#!/usr/bin/env python3
"""
AVRO Integration Client — Final Version
========================================
Bridges Member 1 (Ryu SDN Controller) ↔ Member 3 (AVRO Scheduler API)

Architecture:
  cloud_topology.py  →  /tmp/cloud_host_stats.json
                                    ↓
                     avro_integration_client.py   (this file)
                         ↓                  ↓
              POST /api/schedule     POST /cloud/assign
              (Member 3, port 5000)  (Member 1, port 8080)

Run order:
  Terminal 1: ryu-manager cloud_controller.py --ofp-tcp-listen-port 6633
  Terminal 2: sudo python3 ~/cloud_topology.py
  Terminal 3: cd <member3_project_dir> && python src/scheduler/api.py
  Terminal 4: python3 avro_integration_client.py

Key fix: Member 3's fitness.py expects cpu/memory as 0.0-1.0 fractions.
         Member 1's cloud_topology.py writes them as 0-100 percentages.
         This file converts between them automatically.
"""

import json
import time
import csv
import os
import requests
import random
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
LOG = logging.getLogger('avro_client')

# ── Configuration ────────────────────────────────────────────────────────────
RYU_URL        = "http://localhost:8080"       # Member 1's Ryu controller
AVRO_API_URL   = "http://localhost:5000"       # Member 3's scheduler API
VIRTUAL_IP     = "10.0.100.100"               # clients send tasks here
SERVICE_PORT   = 80
STATS_FILE     = "/tmp/cloud_host_stats.json"  # written by cloud_topology.py
RESULTS_DIR    = "results"
RESULTS_CSV    = os.path.join(RESULTS_DIR, "integration_decisions.csv")
TASK_INTERVAL  = 5     # seconds between tasks
MAX_TASKS      = 0     # 0 = run forever, set to 50 for experiments

# Simulated client IPs (Tenant A hosts)
CLIENTS = ["10.0.1.1", "10.0.1.2", "10.0.1.3", "10.0.1.4"]

# ── Stats reader ─────────────────────────────────────────────────────────────
def read_host_stats(tenant='A'):
    """
    Read VM stats written by cloud_topology.py.

    IMPORTANT: Converts cpu/mem from percentage (0-100) to fraction (0.0-1.0)
    because Member 3's fitness.py expects fractions.

    Returns list of dicts in Member 3's expected format:
      [{ vm_id, cpu, memory, queue_length, delay, timestamp }, ...]
    """
    try:
        with open(STATS_FILE, 'r') as f:
            raw = json.load(f)
    except FileNotFoundError:
        LOG.error("Stats file not found — is cloud_topology.py running?")
        return []
    except json.JSONDecodeError as e:
        LOG.error("Stats file corrupted: %s", e)
        return []

    vm_list = []
    idx = 0
    for name, stats in sorted(raw.items()):   # sort for deterministic order
        if not name.startswith('h'):
            continue
        vm_tenant = stats.get('tenant', 'A')
        if tenant != 'all' and vm_tenant != tenant:
            continue

        # KEY FIX: convert percentage to fraction for Member 3's fitness.py
        cpu_fraction = stats.get('cpu', 0.0) / 100.0
        mem_fraction = stats.get('mem', 0.0) / 100.0

        vm_list.append({
            'vm_id':        idx,            # Member 3 needs integer index
            'name':         name,           # keep name for flow install
            'ip':           stats.get('ip', ''),
            'cpu':          round(cpu_fraction, 4),
            'memory':       round(mem_fraction, 4),
            'queue_length': stats.get('queue_length', 0),
            'delay':        stats.get('delay', 1.0),
            'timestamp':    time.time(),
        })
        idx += 1

    return vm_list

# ── Member 3's AVRO API ───────────────────────────────────────────────────────
def ask_avro(vm_stats_list):
    """
    POST vm_stats to Member 3's scheduler API.
    Returns (selected_vm_id, fitness_score, decision_ms) or (None, None, None).

    Member 3's API: POST /api/schedule
    Expects: list of vm_stat dicts
    Returns: { selected_vm_id, fitness_score, decision_ms, timestamp }
    """
    # Strip internal fields Member 3 doesn't need
    payload = [
        {
            'vm_id':        vm['vm_id'],
            'cpu':          vm['cpu'],
            'memory':       vm['memory'],
            'queue_length': vm['queue_length'],
            'delay':        vm['delay'],
            'timestamp':    vm['timestamp'],
        }
        for vm in vm_stats_list
    ]

    try:
        resp = requests.post(
            f"{AVRO_API_URL}/api/schedule",
            json=payload,
            timeout=5
        )
        if resp.status_code == 200:
            data = resp.json()
            return (
                data.get('selected_vm_id'),
                data.get('fitness_score'),
                data.get('decision_ms')
            )
        LOG.warning("AVRO API HTTP %s: %s", resp.status_code, resp.text)
        return None, None, None
    except requests.exceptions.ConnectionError:
        LOG.error("Cannot reach AVRO API at %s — is src/scheduler/api.py running?", AVRO_API_URL)
        return None, None, None
    except Exception as e:
        LOG.error("AVRO API error: %s", e)
        return None, None, None

# ── Member 1's Ryu flow install ───────────────────────────────────────────────
def install_flow(src_ip, target_ip):
    """Tell Ryu to install a forwarding rule for this task."""
    payload = {
        "src_ip":       src_ip,
        "dst_ip":       VIRTUAL_IP,
        "dst_port":     SERVICE_PORT,
        "protocol":     "tcp",
        "target_vm_ip": target_ip,
    }
    try:
        resp = requests.post(
            f"{RYU_URL}/cloud/assign",
            json=payload,
            timeout=3
        )
        return resp.status_code == 200
    except requests.exceptions.ConnectionError:
        LOG.error("Cannot reach Ryu at %s — is ryu-manager running?", RYU_URL)
        return False
    except Exception as e:
        LOG.error("Flow install error: %s", e)
        return False

# ── Health checks ─────────────────────────────────────────────────────────────
def check_ryu():
    try:
        r = requests.get(f"{RYU_URL}/cloud/health", timeout=2)
        return r.status_code == 200
    except Exception:
        return False

def check_avro():
    try:
        r = requests.get(f"{AVRO_API_URL}/api/status", timeout=2)
        return r.status_code == 200
    except Exception:
        return False

# ── CSV logger for Member 4 ───────────────────────────────────────────────────
def setup_csv():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    if not os.path.exists(RESULTS_CSV):
        with open(RESULTS_CSV, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'task_id', 'timestamp', 'src_ip',
                'chosen_vm_idx', 'chosen_vm_name', 'chosen_ip',
                'cpu_fraction', 'mem_fraction', 'queue_length',
                'fitness_score', 'decision_ms', 'flow_installed'
            ])

def log_row(task_id, src_ip, chosen_vm, selected_idx, fitness, decision_ms, flow_ok):
    with open(RESULTS_CSV, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            task_id,
            time.strftime('%Y-%m-%d %H:%M:%S'),
            src_ip,
            selected_idx,
            chosen_vm.get('name', f"vm{selected_idx}"),
            chosen_vm.get('ip', ''),
            chosen_vm.get('cpu', 0),
            chosen_vm.get('memory', 0),
            chosen_vm.get('queue_length', 0),
            fitness,
            decision_ms,
            flow_ok,
        ])

# ── Main loop ─────────────────────────────────────────────────────────────────
def main():
    LOG.info("=" * 60)
    LOG.info("  AVRO Integration Client")
    LOG.info("  Ryu controller : %s", RYU_URL)
    LOG.info("  AVRO scheduler : %s", AVRO_API_URL)
    LOG.info("  Stats file     : %s", STATS_FILE)
    LOG.info("  Results CSV    : %s", RESULTS_CSV)
    LOG.info("=" * 60)

    # Check Ryu
    LOG.info("Checking Ryu controller...")
    for i in range(10):
        if check_ryu():
            LOG.info("Ryu is up.")
            break
        LOG.warning("Ryu not ready (%d/10)...", i + 1)
        time.sleep(3)
    else:
        LOG.error("Ryu unreachable. Start ryu-manager first.")
        return

    # Check Member 3's AVRO API
    LOG.info("Checking AVRO scheduler API...")
    for i in range(10):
        if check_avro():
            LOG.info("AVRO API is up.")
            break
        LOG.warning("AVRO API not ready (%d/10)...", i + 1)
        time.sleep(3)
    else:
        LOG.error("AVRO API unreachable.")
        LOG.error("Member 3 must run: cd <his_project_dir> && python src/scheduler/api.py")
        return

    setup_csv()
    task_id = 0
    LOG.info("Starting. Press Ctrl+C to stop.")

    try:
        while MAX_TASKS == 0 or task_id < MAX_TASKS:
            task_id += 1
            src_ip = random.choice(CLIENTS)

            LOG.info("─" * 50)
            LOG.info("[Task %d] from %s → %s:%s",
                     task_id, src_ip, VIRTUAL_IP, SERVICE_PORT)

            # Step 1: Read live VM stats from cloud_topology.py
            vm_stats = read_host_stats(tenant='A')
            if not vm_stats:
                LOG.warning("No VM stats — skipping task %d", task_id)
                time.sleep(2)
                continue

            LOG.info("  VM stats (converted to fractions for AVRO):")
            for vm in vm_stats:
                LOG.info("    %-4s  cpu=%.3f  mem=%.3f  queue=%d  delay=%.1fms",
                         vm['name'], vm['cpu'], vm['memory'],
                         vm['queue_length'], vm['delay'])

            # Step 2: Ask Member 3's AVRO API which VM to use
            selected_idx, fitness, decision_ms = ask_avro(vm_stats)
            if selected_idx is None:
                LOG.warning("AVRO decision failed — skipping task %d", task_id)
                time.sleep(2)
                continue

            if selected_idx >= len(vm_stats):
                LOG.warning("AVRO returned out-of-range index %d (have %d VMs)",
                            selected_idx, len(vm_stats))
                continue

            chosen_vm = vm_stats[selected_idx]
            LOG.info("  AVRO chose: %-4s  IP=%-12s  fitness=%.4f  time=%.1fms",
                     chosen_vm['name'], chosen_vm['ip'],
                     fitness or 0, decision_ms or 0)

            # Step 3: Tell Ryu to install the flow
            flow_ok = install_flow(src_ip=src_ip, target_ip=chosen_vm['ip'])
            if flow_ok:
                LOG.info("  Flow installed → traffic routed to %s (%s)",
                         chosen_vm['name'], chosen_vm['ip'])
            else:
                LOG.warning("  Flow install FAILED for task %d", task_id)

            # Step 4: Log everything for Member 4's analysis
            log_row(task_id, src_ip, chosen_vm, selected_idx,
                    fitness, decision_ms, flow_ok)

            time.sleep(TASK_INTERVAL)

    except KeyboardInterrupt:
        LOG.info("\nStopped. %d tasks processed.", task_id)
        LOG.info("Results saved to: %s", RESULTS_CSV)

if __name__ == "__main__":
    main()
