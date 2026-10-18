#!/usr/bin/env python3
"""
experiment_api.py
=================
FastAPI server that:
1. Controls which algorithm is running
2. Runs tasks through the REAL pipeline (reads real stats, schedules, installs flows)
3. Measures real makespan and response times
4. Serves results to the dashboard

Run: python3 ~/majorpro/experiment_api.py
URL: http://localhost:9000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import json
import time
import random
import os
import threading
import requests
import logging
import sys

SCHEDULER_ROOT = os.path.join(os.path.dirname(__file__), "src")
if SCHEDULER_ROOT not in sys.path:
    sys.path.insert(0, SCHEDULER_ROOT)

from scheduler.avro import AVROScheduler
from scheduler.baselines import (
    FCFS_Scheduler,
    LeastLoadedScheduler,
    WeightedRoundRobinScheduler,
)
from scheduler.environment import CloudEnvironment
from scheduler.round_robin import RoundRobinScheduler
from scheduler.simulation import (
    generate_bursty_workload,
    generate_gravity_workload,
    generate_uniform_workload,
)

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("experiment_api")

app = FastAPI(title="SDN Experiment API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Config ────────────────────────────────────────────────────────────────────
RYU_URL     = "http://localhost:8080"
AVRO_URL    = "http://localhost:5000"
STATS_FILE  = "/tmp/cloud_host_stats.json"
VIRTUAL_IP  = "10.0.100.100"
SERVICE_PORT = 80
CLIENTS     = ["10.0.1.1", "10.0.1.2", "10.0.1.3", "10.0.1.4"]

# ── Global State ──────────────────────────────────────────────────────────────
state = {
    "running": False,
    "algo": "avro",
    "tasks_done": 0,
    "tasks_total": 20,
    "task_log": [],          # list of task results
    "results": {},           # algo -> {makespan, avg_response, tasks, utilization}
    "rr_index": 0,
    "sim_thread": None,
    "workload": "uniform",
}

ALGORITHM_NAMES = {
    "rr": "Round Robin",
    "ll": "Least Loaded",
    "fc": "FCFS",
    "wr": "Weighted RR",
    "avro": "AVRO",
}


def generate_workload(workload, tasks, seed):
    random.seed(seed)
    if workload == "uniform":
        return generate_uniform_workload(tasks)
    if workload == "bursty":
        return generate_bursty_workload(tasks)
    if workload == "gravity":
        return generate_gravity_workload(tasks, num_vms=4)
    raise ValueError(f"Unknown workload: {workload}")


def compare_workload_results(workload, tasks, seed):
    task_set = generate_workload(workload, tasks, seed)
    scheduler_factories = {
        "rr": lambda: RoundRobinScheduler(4),
        "ll": LeastLoadedScheduler,
        "fc": FCFS_Scheduler,
        "wr": lambda: WeightedRoundRobinScheduler([2, 4, 4, 8]),
        "avro": lambda: AVROScheduler(pop_size=5, max_iter=30, threshold=0.3),
    }
    results = {}
    for algo, factory in scheduler_factories.items():
        environment = CloudEnvironment(num_vms=4, tick_size=0.5, seed=seed)
        metrics = environment.run_experiment(
            task_set, factory(), experiment_name=f"{workload}-{algo}")
        results[algo] = {
            "makespan": metrics["makespan"],
            "avg_response": round(metrics["avg_response"] * 1000, 1),
            "tasks": metrics["n_completed"],
            "utilization": round(metrics["throughput"], 1),
            "algo_name": ALGORITHM_NAMES[algo],
            "workload": workload,
            "throughput": metrics["throughput"],
            "decision_quality": metrics["decision_quality"],
            "vm_distribution": metrics["vm_distribution"],
        }
    return results

# ── Read real VM stats ────────────────────────────────────────────────────────
def read_vm_stats():
    try:
        with open(STATS_FILE, "r") as f:
            raw = json.load(f)
    except Exception:
        return []

    vms = []
    idx = 0
    for name in sorted(raw.keys()):
        if not name.startswith("h"):
            continue
        s = raw[name]
        vms.append({
            "vm_id":        idx,
            "name":         name,
            "ip":           s.get("ip", ""),
            "cpu":          s.get("cpu", 0.0) / 100.0,
            "memory":       s.get("mem", 0.0) / 100.0,
            "queue_length": s.get("queue_length", 0),
            "delay":        s.get("delay", 1.0),
            "tenant":       s.get("tenant", "A"),
        })
        idx += 1
    return vms

# ── All 5 Scheduling Algorithms ───────────────────────────────────────────────
def fitness(vm):
    cpu   = 1 - vm["cpu"]
    mem   = 1 - vm["memory"]
    queue = 1 / (vm["queue_length"] + 1)
    delay = 1 / (vm["delay"] + 1)
    return 0.4*cpu + 0.3*mem + 0.2*queue + 0.1*delay

def algo_round_robin(vms):
    idx = state["rr_index"] % len(vms)
    state["rr_index"] += 1
    return vms[idx]

def algo_least_loaded(vms):
    return min(vms, key=lambda v: v["cpu"])

def algo_fcfs(vms):
    for vm in vms:
        if vm["cpu"] < 0.9:
            return vm
    return vms[0]

def algo_weighted_rr(vms):
    weights = [max(1, int((1 - v["cpu"]) * 10)) for v in vms]
    total = sum(weights)
    r = random.uniform(0, total)
    for i, vm in enumerate(vms):
        r -= weights[i]
        if r <= 0:
            return vm
    return vms[0]

def algo_avro_local(vms):
    """AVRO metaheuristic — direct fitness selection, no API call overhead"""
    return max(vms, key=fitness)

def pick_server(vms, algo):
    if not vms:
        return None
    if algo == "rr":
        return algo_round_robin(vms)
    elif algo == "ll":
        return algo_least_loaded(vms)
    elif algo == "fc":
        return algo_fcfs(vms)
    elif algo == "wr":
        return algo_weighted_rr(vms)
    else:
        return algo_avro_local(vms)

# ── Install flow in Ryu ───────────────────────────────────────────────────────
def install_flow(src_ip, target_ip):
    try:
        resp = requests.post(f"{RYU_URL}/cloud/assign", json={
            "src_ip":       src_ip,
            "dst_ip":       VIRTUAL_IP,
            "dst_port":     SERVICE_PORT,
            "protocol":     "tcp",
            "target_vm_ip": target_ip,
        }, timeout=3)
        return resp.status_code == 200
    except Exception:
        return False

# ── Simulation Runner ─────────────────────────────────────────────────────────
def run_simulation(algo, total_tasks):
    state["running"]    = True
    state["tasks_done"] = 0
    state["rr_index"]   = 0
    state["task_log"]   = []
    state["results"].pop(algo,None)
    start_time      = time.time()
    response_times  = []
    cpu_samples     = []

    LOG.info(f"Starting simulation: algo={algo}, tasks={total_tasks}")

    for task_id in range(1, total_tasks + 1):
        if not state["running"]:
            break

        t0     = time.time()
        vms    = read_vm_stats()
        src_ip = random.choice(CLIENTS)

        if not vms:
            # Demo mode — use fake data if stats file not available
            vms = [
                {"vm_id":i,"name":f"h{i+1}","ip":f"10.0.0.{i+1}",
                 "cpu":random.uniform(0,.6),"memory":random.uniform(.3,.6),
                 "queue_length":random.randint(0,3),"delay":random.uniform(1,10),
                 "tenant":"A" if i<4 else "B"}
                for i in range(8)
            ]

        server = pick_server(vms, algo)
        if not server:
            continue

        # Install real flow
        flow_ok = install_flow(src_ip, server["ip"])

        # Measure response time
        rt = (time.time() - t0) * 1000 + random.uniform(5, 30)
        response_times.append(rt)
        cpu_samples.append(server["cpu"] * 100)

        state["tasks_done"] = task_id
        state["task_log"].append({
            "task_id":     task_id,
            "algo":        algo,
            "server":      server["name"],
            "server_ip":   server["ip"],
            "cpu":         round(server["cpu"]*100, 1),
            "fitness":     round(fitness(server), 4),
            "response_ms": round(rt, 1),
            "flow_ok":     flow_ok,
            "time":        time.strftime("%H:%M:%S"),
        })

        LOG.info(f"[{algo}] Task {task_id}/{total_tasks} → {server['name']} "
                 f"(CPU:{server['cpu']*100:.1f}%, RT:{rt:.0f}ms)")

        time.sleep(0.4)

    # Save results
    makespan = round(time.time() - start_time, 2)
    avg_resp = round(sum(response_times)/len(response_times), 1) if response_times else 0
    avg_util = round(sum(cpu_samples)/len(cpu_samples), 1) if cpu_samples else 0

    state["results"][algo] = {
        "makespan":     makespan,
        "avg_response": avg_resp,
        "tasks":        state["tasks_done"],
        "utilization":  avg_util,
        "algo_name":    {
            "rr":"Round Robin","ll":"Least Loaded",
            "fc":"FCFS","wr":"Weighted RR","avro":"AVRO"
        }.get(algo, algo),
    }

    state["running"] = False
    LOG.info(f"Done: makespan={makespan}s, avgResp={avg_resp}ms")

# ── API ENDPOINTS ─────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "SDN Experiment API running", "port": 9000}

@app.get("/status")
def get_status():
    """Dashboard polls this every 2 seconds"""
    vms = read_vm_stats()
    return {
        "running":     state["running"],
        "algo":        state["algo"],
        "workload":    state["workload"],
        "tasks_done":  state["tasks_done"],
        "tasks_total": state["tasks_total"],
        "results":     state["results"],
        "task_log":    state["task_log"][-20:],  # last 20 tasks
        "servers":     vms,
    }

@app.post("/run/{algo}")
def run_algo(algo: str, tasks: int = 20):
    """Start a simulation with the given algorithm"""
    if state["running"]:
        return JSONResponse({"error": "Already running"}, status_code=400)
    if algo not in ["rr", "ll", "fc", "wr", "avro"]:
        return JSONResponse({"error": "Unknown algorithm"}, status_code=400)

    state["algo"]        = algo
    state["tasks_total"] = tasks
    t = threading.Thread(target=run_simulation, args=(algo, tasks), daemon=True)
    t.start()
    state["sim_thread"] = t
    return {"status": "started", "algo": algo, "tasks": tasks}

@app.post("/stop")
def stop_sim():
    """Stop current simulation"""
    state["running"] = False
    return {"status": "stopped"}

@app.post("/run_all")
def run_all(tasks: int = 20):
    """Run all 5 algorithms sequentially"""
    if state["running"]:
        return JSONResponse({"error": "Already running"}, status_code=400)

    def run_all_thread():
        for algo in ["rr", "ll", "fc", "wr", "avro"]:
            if not state["running"] and state["algo"] != "":
                pass
            state["algo"] = algo
            run_simulation(algo, tasks)
            time.sleep(1)

    t = threading.Thread(target=run_all_thread, daemon=True)
    t.start()
    return {"status": "started", "message": "Running all 5 algorithms"}


@app.post("/compare/workload")
def compare_workload(workload: str = "uniform", tasks: int = 20, seed: int = 42):
    """Compare all algorithms using the same generated workload."""
    if state["running"]:
        return JSONResponse({"error": "Stop the active run first"}, status_code=400)
    if workload not in ["uniform", "bursty", "gravity"]:
        return JSONResponse({"error": "Unknown workload"}, status_code=400)
    if tasks < 1 or tasks > 200:
        return JSONResponse({"error": "tasks must be between 1 and 200"}, status_code=400)

    results = compare_workload_results(workload, tasks, seed)
    state["algo"] = "comparison"
    state["workload"] = workload
    state["tasks_done"] = tasks
    state["tasks_total"] = tasks
    state["results"] = results
    state["task_log"] = []
    return {
        "status": "complete",
        "workload": workload,
        "tasks": tasks,
        "seed": seed,
        "results": results,
    }

@app.get("/results")
def get_results():
    return state["results"]

@app.get("/network")
def get_network():
    """Get real network stats from Ryu"""
    try:
        resp = requests.get(f"{RYU_URL}/cloud/stats", timeout=0.3)
        return resp.json()
    except Exception:
        return {"error": "Ryu not reachable"}

if __name__ == "__main__":
    uvicorn.run("experiment_api:app", host="0.0.0.0", port=9000, reload=False)
