#!/usr/bin/env python3
"""Capture and plot a live Mininet AVRO-versus-Round-Robin experiment.

Every sample reads host/switch state from Ryu, requests an AVRO decision, and
installs AVRO and Round Robin flows. Matching PNG, CSV and JSON records are
written to ``results/live_mininet_<timestamp>``.
"""

import argparse
import csv
import json
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.scheduler.fitness import compute_fitness

RESULTS_DIR = ROOT / "results"
RYU_URL = "http://127.0.0.1:8080"
SCHEDULER_URL = "http://127.0.0.1:5000"
VIRTUAL_IP = "10.0.100.100"
SERVICE_PORT = 80


def get_live_hosts():
    response = requests.get(f"{RYU_URL}/cloud/stats", timeout=3)
    response.raise_for_status()
    payload = response.json()
    raw = payload.get("host_stats", {})
    timestamp = raw.get("_timestamp")
    if timestamp is None or time.time() - float(timestamp) > 10:
        raise RuntimeError("Mininet host stats are unavailable or older than 10 seconds")
    hosts = []
    for name in ("h1", "h2", "h3", "h4"):
        stat = raw.get(name)
        if stat is None:
            raise RuntimeError(f"Missing live statistics for {name}")
        hosts.append({
            "vm_id": len(hosts), "name": name, "ip": stat.get("ip", ""),
            "cpu": max(0.0, min(1.0, float(stat.get("cpu", 0.0)) / 100.0)),
            "memory": max(0.0, min(1.0, float(stat.get("mem", 0.0)) / 100.0)),
            "queue_length": int(stat.get("queue_length", 0)),
            "delay": float(stat.get("delay", 1.0)),
            "rx_bytes": int(stat.get("rx_bytes", 0)),
            "tx_bytes": int(stat.get("tx_bytes", 0)),
            "tenant": stat.get("tenant", "A"),
        })
    return hosts, payload


def choose_avro(hosts):
    metrics = ("vm_id", "cpu", "memory", "queue_length", "delay")
    response = requests.post(
        f"{SCHEDULER_URL}/api/schedule",
        json={"vms": [{key: host[key] for key in metrics} for host in hosts]},
        timeout=5,
    )
    response.raise_for_status()
    decision = response.json()
    index = int(decision["selected_vm_id"])
    if not 0 <= index < len(hosts):
        raise RuntimeError(f"Scheduler returned invalid VM index {index}")
    return index, decision


def install_flow(source_ip, target_ip):
    response = requests.post(f"{RYU_URL}/cloud/assign", json={
        "src_ip": source_ip, "dst_ip": VIRTUAL_IP, "dst_port": SERVICE_PORT,
        "protocol": "tcp", "target_vm_ip": target_ip,
    }, timeout=3)
    return response.status_code == 200, response.status_code, response.text.strip()


def capture(samples, interval, source_ip):
    records, rr_index = [], 0
    started = time.monotonic()
    for sample in range(1, samples + 1):
        hosts, controller = get_live_hosts()
        avro_index, decision = choose_avro(hosts)
        rr_selected = rr_index % len(hosts)
        rr_index += 1
        avro_ok, avro_status, avro_response = install_flow(source_ip, hosts[avro_index]["ip"])
        rr_ok, rr_status, rr_response = install_flow(source_ip, hosts[rr_selected]["ip"])
        avro_host, rr_host = hosts[avro_index], hosts[rr_selected]
        record = {
            "sample": sample, "captured_at": datetime.now().isoformat(timespec="seconds"),
            "elapsed_s": round(time.monotonic() - started, 2),
            "avro_vm": avro_host["name"], "avro_vm_ip": avro_host["ip"],
            "avro_fitness": round(float(decision.get("fitness_score", compute_fitness(avro_host))), 4),
            "avro_decision_ms": round(float(decision.get("decision_ms", 0.0)), 3),
            "avro_flow_installed": avro_ok, "avro_flow_status": avro_status,
            "avro_flow_response": avro_response,
            "rr_vm": rr_host["name"], "rr_vm_ip": rr_host["ip"],
            "rr_fitness": round(compute_fitness(rr_host), 4),
            "rr_flow_installed": rr_ok, "rr_flow_status": rr_status,
            "rr_flow_response": rr_response,
            "switch_count": len(controller.get("switches", {})),
            "allowed_packets": int(controller.get("allowed_pkts", 0)),
            "blocked_packets": int(controller.get("blocked_pkts", 0)),
            "flow_count": sum(len(flows) for flows in controller.get("flow_stats", {}).values()),
            "hosts": hosts,
        }
        records.append(record)
        print(f"  sample {sample:>3}/{samples}: AVRO={avro_host['name']} ({record['avro_fitness']:.4f}), "
              f"RR={rr_host['name']} ({record['rr_fitness']:.4f})", flush=True)
        if sample < samples and interval:
            time.sleep(interval)
    return records


def write_csv(records, path):
    fields = [key for key in records[0] if key != "hosts"]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({key: record[key] for key in fields} for record in records)


def plot_results(records, path):
    samples = np.array([r["sample"] for r in records])
    avro = np.array([r["avro_fitness"] for r in records])
    rr = np.array([r["rr_fitness"] for r in records])
    labels = ["h1", "h2", "h3", "h4"]
    avro_counts, rr_counts = Counter(r["avro_vm"] for r in records), Counter(r["rr_vm"] for r in records)
    fig, axes = plt.subplots(2, 2, figsize=(14, 9), constrained_layout=True)
    fig.suptitle("Live Mininet: AVRO vs Round Robin (Tenant A: h1–h4)", fontweight="bold")
    axes[0, 0].plot(samples, avro, label="AVRO", color="#1976d2", lw=1.8)
    axes[0, 0].plot(samples, rr, label="Round Robin", color="#d32f2f", lw=1.4, alpha=.8)
    axes[0, 0].set(title="Fitness per live scheduling decision", xlabel="Sample", ylabel="Fitness", ylim=(0, 1))
    axes[0, 0].grid(alpha=.25); axes[0, 0].legend()
    axes[0, 1].plot(samples, np.cumsum(avro) / samples, label="AVRO", color="#1976d2", lw=2)
    axes[0, 1].plot(samples, np.cumsum(rr) / samples, label="Round Robin", color="#d32f2f", lw=1.7)
    axes[0, 1].set(title="Cumulative average fitness", xlabel="Sample", ylabel="Average fitness", ylim=(0, 1))
    axes[0, 1].grid(alpha=.25); axes[0, 1].legend()
    positions, width = np.arange(len(labels)), .36
    axes[1, 0].bar(positions - width / 2, [avro_counts[x] for x in labels], width, label="AVRO", color="#1976d2")
    axes[1, 0].bar(positions + width / 2, [rr_counts[x] for x in labels], width, label="Round Robin", color="#d32f2f")
    axes[1, 0].set(title="Live VM selection distribution", xlabel="VM", ylabel="Assignments", xticks=positions, xticklabels=labels)
    axes[1, 0].grid(alpha=.25, axis="y"); axes[1, 0].legend()
    for index, label in enumerate(labels):
        axes[1, 1].plot(samples, [r["hosts"][index]["cpu"] * 100 for r in records], label=label, lw=1.5)
    axes[1, 1].set(title="Measured CPU utilization", xlabel="Sample", ylabel="CPU (%)", ylim=(0, 100))
    axes[1, 1].grid(alpha=.25); axes[1, 1].legend(ncol=2)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def print_summary(records, png_path, csv_path, json_path):
    avro = np.array([r["avro_fitness"] for r in records])
    rr = np.array([r["rr_fitness"] for r in records])
    improvement = (avro.mean() - rr.mean()) / rr.mean() * 100 if rr.mean() else 0.0
    avro_flows = sum(r["avro_flow_installed"] for r in records)
    rr_flows = sum(r["rr_flow_installed"] for r in records)
    print("\nLive result summary")
    print(f"  samples: {len(records)} | switches observed: {records[-1]['switch_count']}")
    print(f"  mean fitness: AVRO {avro.mean():.4f} | Round Robin {rr.mean():.4f} | improvement {improvement:.2f}%")
    print(f"  flow installs: AVRO {avro_flows}/{len(records)} | Round Robin {rr_flows}/{len(records)}")
    print(f"  PNG:  {png_path}\n  CSV:  {csv_path}\n  JSON: {json_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--source-ip", default="10.0.0.1")
    args = parser.parse_args()
    if args.samples < 1 or args.interval < 0:
        parser.error("--samples must be positive and --interval must be non-negative")
    try:
        records = capture(args.samples, args.interval, args.source_ip)
    except (requests.RequestException, RuntimeError, KeyError, ValueError) as exc:
        parser.error(f"live capture failed: {exc}")
    RESULTS_DIR.mkdir(exist_ok=True)
    stem = RESULTS_DIR / f"live_mininet_{datetime.now():%Y%m%d_%H%M%S}"
    json_path, csv_path, png_path = stem.with_suffix(".json"), stem.with_suffix(".csv"), stem.with_suffix(".png")
    json_path.write_text(json.dumps(records, indent=2) + "\n")
    write_csv(records, csv_path)
    plot_results(records, png_path)
    print_summary(records, png_path, csv_path, json_path)


if __name__ == "__main__":
    main()
