# SDN-Cloud-Optimizer

An adaptive SDN-based framework for intelligent load balancing and task scheduling in cloud environments using the AVRO (African Vulture Routing Optimization) metaheuristic algorithm.

---

## Overview

This framework integrates Software-Defined Networking with metaheuristic optimization to intelligently schedule tasks across virtual machines in a cloud data center. The AVRO algorithm selects the best VM for each incoming task using a multi-metric fitness function that considers CPU utilization, memory usage, queue length, and network delay — outperforming traditional schedulers by 17–29% in response time.

**Architecture:**

```
Mininet Topology  →  /tmp/cloud_host_stats.json
                               ↓
                  avro_integration_client.py
                        ↓              ↓
             POST /api/schedule   POST /cloud/assign
             (AVRO, port 5000)    (Ryu, port 8080)
                                       ↓
                     OpenFlow flow rules installed in OVS switches
```

---

## System Requirements

- Python 3.11
- Ryu 4.34
- Mininet 2.3.1b4
- Open vSwitch 3.7+
- Arch Linux / Ubuntu 20.04+

---

## Installation

**1. Create and activate virtual environment:**
```bash
python3.11 -m venv ~/ryu-env
source ~/ryu-env/bin/activate
```

**2. Install dependencies in order:**
```bash
pip install "setuptools==67.6.0" "wheel==0.38.4"
pip install ryu==4.34
pip install "eventlet==0.33.3"
pip install numpy matplotlib networkx scikit-learn requests
```

**3. Patch Ryu eventlet compatibility:**
```bash
sed -i 's/from eventlet.wsgi import ALREADY_HANDLED/ALREADY_HANDLED = b""/' \
    ~/ryu-env/lib/python3.11/site-packages/ryu/app/wsgi.py
```

**4. Verify:**
```bash
ryu-manager --version   # should print: ryu-manager 4.34
sudo mn --version       # should print: 2.3.1b4
```

**5. Start Open vSwitch (if not already running):**
```bash
sudo ovsdb-server --remote=punix:/run/openvswitch/db.sock \
    --remote=db:Open_vSwitch,Open_vSwitch,manager_options \
    --pidfile --detach
sudo ovs-vswitchd --pidfile --detach
sudo ovs-vsctl show     # should return without error
```

---

## Running the Project

Open **6 terminals**. Run `source ~/ryu-env/bin/activate` in every terminal before starting.

**Pre-run cleanup (always do this first):**
```bash
sudo mn -c
```

---

### Terminal 1 — Ryu SDN Controller
```bash
source ~/ryu-env/bin/activate
cd ~/cloud-sdn-avro
ryu-manager controller/cloud_controller.py --ofp-tcp-listen-port 6633
```
Wait for: `wsgi starting up on http://0.0.0.0:8080`

---

### Terminal 2 — Mininet Topology
```bash
cd ~/cloud-sdn-avro
sudo python3 topology/cloud_topology.py
```
Wait for: `Host stats monitor running -> /tmp/cloud_host_stats.json`

You will get a `mininet>` prompt — keep this terminal open.

---

### Terminal 3 — AVRO Scheduler API
```bash
source ~/ryu-env/bin/activate
cd ~/cloud-sdn-avro/SDN-Cloud-Optimizer
python src/scheduler/api.py
```
Wait for: `Scheduler API running on http://0.0.0.0:5000`

---

### Terminal 4 — Integration Client
```bash
source ~/ryu-env/bin/activate
cd ~/cloud-sdn-avro
python3 integration/avro_integration_client.py
```
Wait for: `Ryu is up. AVRO API is up. Starting.`

This bridges Mininet stats → AVRO decision → Ryu flow install.

---

### Terminal 5 — Live Stats Monitor
```bash
watch -n 2 cat /tmp/cloud_host_stats.json
```

---

### Browser — Dashboard
Open `~/cloud-sdn-avro/dashboard.html` in Firefox.

Connects to `http://localhost:8080/cloud/stats` and shows live topology, VM metrics, flow stats, and firewall blocks.

---

## Demo Scenarios

Run these inside the Mininet CLI (Terminal 2):

**Normal load — AVRO distributes freely:**
```
mininet> killall stress
```

**Two hosts stressed — AVRO avoids them:**
```
mininet> h1 stress --cpu 4 &
mininet> h2 stress --cpu 4 &
```

**Three hosts stressed — AVRO picks only h4:**
```
mininet> h3 stress --cpu 4 &
```

**Stop stress on all hosts:**
```
mininet> h1 killall stress
mininet> h2 killall stress
mininet> h3 killall stress
mininet> h4 killall stress
```

**Firewall demo (cross-tenant traffic blocked):**
```
mininet> h1 ping -c5 h5    # BLOCKED — Tenant A → Tenant B
mininet> h1 ping -c5 h2    # ALLOWED — same tenant
```

---

## Run Experiments

Generates comparison graphs for AVRO vs Round Robin vs LeastLoaded vs FCFS vs WeightedRR across Uniform, Bursty, and Gravity workloads:

```bash
source ~/ryu-env/bin/activate
cd ~/cloud-sdn-avro/SDN-Cloud-Optimizer
python results/run_experiment.py
```

Output saved to `results/full_comparison.png`.

---

## Run Tests

```bash
source ~/ryu-env/bin/activate
cd ~/cloud-sdn-avro/SDN-Cloud-Optimizer
python tests/test_avro.py        # 21 AVRO algorithm tests
python tests/test_fitness.py     # 6 fitness function tests
python tests/test_round_robin.py # 6 baseline tests
python tests/test_connector.py   # 8 data connector tests
```

---

## Shutdown Order

```
Terminal 4: Ctrl+C  (stop integration client)
Terminal 3: Ctrl+C  (stop scheduler API)
Terminal 2: exit    (stop Mininet)
Terminal 1: Ctrl+C  (stop Ryu)

Then: sudo mn -c
```

---

## Project Structure

```
controller/
  cloud_controller.py         Ryu SDN app — firewall, REST API, flow management
topology/
  cloud_topology.py           8-host Mininet 3-tier data center topology
integration/
  avro_integration_client.py  Bridge: Mininet stats → AVRO → Ryu flow install
monitoring/
  cgroup_cpu_monitor.py       Per-host CPU monitoring via cgroup
src/scheduler/
  avro.py                     AVRO optimizer (population, exploration, development)
  fitness.py                  Multi-metric VM fitness function
  api.py                      REST API for scheduler (port 5000)
  baselines.py                LeastLoaded, WeightedRR, FCFS baselines
  round_robin.py              Round Robin baseline
  connector.py                Data bridge (simulation ↔ live Mininet)
  environment.py              Simulation harness for experiments
  simulation.py               Workload generators (uniform, bursty, gravity)
  vm_state.py                 Dynamic VM state manager
src/monitor/
  resource_monitor.py         VM resource monitoring module
  openflow_stats.py           OpenFlow port statistics collector
monitor_server.py             HTTP API wrapper for resource monitor (port 6000)
dashboard.html                Live network monitoring dashboard
results/
  run_experiment.py           Full comparison experiment runner
  plot_convergence.py         Convergence and distribution plots
  integration_decisions.csv   Live run decision log
tests/                        45 unit and integration tests
```

---

## API Reference

**Scheduler API** (port 5000):
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/schedule` | Submit VM stats, receive scheduling decision |
| GET | `/api/log` | Retrieve full decision history |
| GET | `/api/status` | Health check |

**Ryu Controller API** (port 8080):
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/cloud/stats` | All switch stats + host metrics |
| GET | `/cloud/health` | Health check |
| POST | `/cloud/assign` | Install forwarding rule for scheduled task |

**Monitor API** (port 6000):
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/vm_stats` | Current VM resource stats |
| POST | `/api/task_assigned` | Notify task assignment (updates queue) |
| POST | `/api/task_completed` | Notify task completion (decrements queue) |

---

## VM Stats Data Contract

```python
vm_stats = {
    'vm_id':        int,    # 0–3
    'cpu':          float,  # 0.0–1.0 (fraction, not percentage)
    'memory':       float,  # 0.0–1.0
    'queue_length': int,    # tasks currently waiting
    'delay':        float,  # milliseconds
    'timestamp':    float   # Unix time
}
```

**Note:** `cloud_topology.py` writes CPU as 0–100%. `avro_integration_client.py` converts to 0.0–1.0 fractions automatically before sending to the scheduler.

---

## Fitness Function

```
Fitness(vm) = 0.4 × (1 − CPU) + 0.3 × (1 − Memory) + 0.2 / (Queue + 1) + 0.1 / (Delay + 1)
```

Higher score = better candidate for task assignment. Score range: (0, 1].

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ryu-manager: ALREADY_HANDLED ImportError` | Run the eventlet wsgi.py sed patch above |
| `ovsdb-server: already running` | OVS is already up — proceed normally |
| `Stats file not found` | Topology not started yet (Terminal 2) |
| `AVRO API unreachable` | Start `python src/scheduler/api.py` (Terminal 3) |
| `Connection refused :8080` | Ryu not started or still initializing |
| Mininet fails to start | Run `sudo mn -c` then retry |
| `git branch -a` hangs | Run `git config --global core.pager cat` |
