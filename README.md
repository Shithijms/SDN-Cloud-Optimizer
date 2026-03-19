# 🧠 SDN-Based Intelligent Load Balancing and Task Scheduling Framework

![Python](https://img.shields.io/badge/Python-3.8-blue.svg)
![Mininet](https://img.shields.io/badge/Mininet-2.3.0-green.svg)
![Ryu](https://img.shields.io/badge/Ryu-4.34-yellow.svg)
![License](https://img.shields.io/badge/License-MIT-red.svg)

---

## 📌 Overview

This project implements an **Adaptive SDN-Based Framework for Intelligent Load Balancing and Task Scheduling in Cloud Environments**.

It integrates:

- Software-Defined Networking (SDN)
- Metaheuristic Optimization (AVRO-based)
- Real-time resource monitoring
- Dynamic OpenFlow rule management

The framework intelligently selects Virtual Machines (VMs) for task execution using an **AVRO (African Vulture Routing Optimization)** inspired algorithm, while simultaneously managing network paths through an SDN controller.

**Team Size:** 4 Members  
**Duration:** 5 Months  
**Status:** 🚧 In Development  

---

## 🎯 Key Features

- 🏗 **SDN-Controlled Cloud Data Center**  
  3-tier topology (Core → Aggregation → Edge) emulated in Mininet  

- 📊 **Real-Time Resource Monitoring**  
  Collects:
  - CPU Utilization
  - Memory Usage
  - Queue Length
  - Network Delay

- 🧠 **AVRO-Based Intelligent Scheduler**  
  Population-based metaheuristic VM selection (Primary Contribution)

- 🔁 **Dynamic Flow Rule Installation**  
  OpenFlow rules installed dynamically via Ryu controller

- 🎯 **Multi-Objective Optimization**
  Optimizes:
  - Makespan
  - Average Response Time
  - Resource Utilization Balance

- 📈 **Comparative Evaluation**
  - Round Robin (Baseline)
  - Optional ML-based scheduler

---

## 🏗 System Architecture

```
Workload Layer
(iPerf3 / Custom Task Generator)
            │
            ▼
SDN Controller (Ryu)
 ├── AVRO Scheduling Module
 │     • VM Fitness Computation
 │     • Population-Based Optimization
 │     • Best VM Selection
 │
 ├── Resource Monitor Module
 │     • OpenFlow Port Stats
 │     • VM CPU/Memory Polling
 │     • Queue Length Detection
 │
 └── Flow Rule Manager
       • Path Computation
       • OpenFlow Rule Installation
            │
            ▼
Mininet 3-Tier Data Center Topology
Core → Aggregation → Edge → VMs
```

---

## 🧮 Mathematical Model

### 🎯 Optimization Objective

\[
Z = \alpha \cdot Makespan + \beta \cdot AvgResponseTime + \gamma \cdot U_{std}
\]

Where:

- **Makespan** → Total completion time of all tasks  
- **AvgResponseTime** → Mean task response time  
- **Ustd** → Standard deviation of VM utilization  
- **α, β, γ** → Tunable weight parameters  

---

### 🧠 VM Fitness Function (AVRO Selection)

\[
Fitness_{vm} =
w_1(1 - CPU_{util})
+ w_2(1 - Mem_{util})
+ w_3\frac{1}{QueueLen+1}
+ w_4\frac{1}{Delay+1}
\]

This ensures selection of:
- Low CPU usage VMs
- Low memory usage VMs
- Small queue length
- Low network delay

---

## 📁 Repository Structure

```
sdn-load-balancing-framework/
│
├── topology/
│   ├── datacenter_topo.py
│   └── topo_config.yaml
│
├── controller/
│   ├── ryu_app.py
│   ├── flow_manager.py
│   └── packet_handler.py
│
├── scheduler/
│   ├── avro_scheduler.py
│   ├── round_robin.py
│   ├── rf_scheduler.py
│   └── fitness.py
│
├── monitoring/
│   ├── resource_monitor.py
│   ├── network_monitor.py
│   └── data_logger.py
│
├── evaluation/
│   ├── metrics.py
│   ├── experiment_runner.py
│   └── visualization.py
│
├── workloads/
│   ├── traffic_generator.py
│   ├── task_generator.py
│   └── workload_configs/
│
├── results/
│   ├── figures/
│   ├── logs/
│   └── reports/
│
├── tests/
│   ├── test_avro.py
│   ├── test_monitoring.py
│   └── test_integration.py
│
├── docs/
│   ├── architecture.md
│   ├── api_reference.md
│   └── experiment_design.md
│
├── requirements.txt
├── setup.sh
├── CONTRIBUTING.md
├── LICENSE
└── README.md
```

---

## 🚀 Getting Started

### 📦 Prerequisites

- Ubuntu 20.04 / 22.04  
- Python 3.8+  
- Mininet 2.3.0  
- Ryu Controller 4.34  
- Open vSwitch  

---

## 🔧 Installation

### 1️⃣ Clone Repository

```bash
git clone https://github.com/Shithijms/SDN-Cloud-Optimizer.git
cd SDN-Cloud-Optimizer
```

### 2️⃣ Run Setup Script

```bash
chmod +x setup.sh
./setup.sh
```

### 3️⃣ Verify Installation

Test Mininet:

```bash
sudo mn --test pingall
```

Test Ryu:

```bash
ryu-manager --version
```

Install Python Dependencies:

```bash
pip install -r requirements.txt
```

---

## 💻 Usage

### 1️⃣ Start SDN Controller

```bash
ryu-manager controller/ryu_app.py
```

### 2️⃣ Launch Mininet Topology

```bash
sudo python topology/datacenter_topo.py
```

### 3️⃣ Start Resource Monitoring

```bash
python monitoring/resource_monitor.py --interval 2
```

### 4️⃣ Generate Workload

```bash
python workloads/task_generator.py --workload medium --duration 300
```

### 5️⃣ Run Full Experiment Suite

```bash
python evaluation/experiment_runner.py \
    --algorithms avro round_robin \
    --workloads low medium high \
    --repeats 5
```

### 6️⃣ Generate Visualizations

```bash
python evaluation/visualization.py --results-dir results/logs/
```

---

## 📊 Evaluation Metrics

- Makespan  
- Throughput  
- Average Response Time  
- Resource Utilization Variance  
- Load Distribution Fairness  

---

