# 🧠 SDN-Based Intelligent Load Balancing and Task Scheduling Framework

[![Python](https://img.shields.io/badge/Python-3.8-blue.svg)](https://www.python.org/)
[![Mininet](https://img.shields.io/badge/Mininet-2.3.0-green.svg)](https://mininet.org/)
[![Ryu](https://img.shields.io/badge/Ryu-4.34-yellow.svg)](https://ryu-sdn.org/)
[![License](https://img.shields.io/badge/License-MIT-red.svg)](LICENSE)

## 📋 Overview

This project implements an **Adaptive SDN-Based Framework for Intelligent Load Balancing and Task Scheduling in Cloud Environments**. It combines Software-Defined Networking (SDN) with metaheuristic optimization to dynamically allocate cloud resources and balance network traffic.

The framework uses an **AVRO (African Vulture Routing Optimization)**-inspired algorithm to make intelligent VM selection decisions based on real-time resource metrics, while simultaneously managing network paths through SDN flow rules.

**Team Size:** 4 Members  
**Timeline:** 5 Months  
**Status:** In Development

---

## 🎯 Key Features

- **SDN-Controlled Cloud Data Center** – 3-tier network topology (Core, Aggregation, Edge) emulated in Mininet
- **Real-Time Resource Monitoring** – Collects CPU, memory, queue length, and network delay from VM hosts
- **AVRO-Based Intelligent Scheduler** – Metaheuristic optimization for VM selection (primary contribution)
- **Dynamic Flow Rule Installation** – Ryu controller installs OpenFlow rules based on scheduling decisions
- **Multi-Objective Optimization** – Balances makespan, response time, and resource utilization
- **Comprehensive Evaluation** – Comparison against Round Robin and (optionally) ML-based schedulers

---

## 🏗️ System Architecture
┌──────────────────────────────────────────────────┐
│                    Workload Layer                 │
│         (iPerf3 / Custom Task Generator)         │
└────────────────────┬─────────────────────────────┘
                     │ Task Arrival
┌────────────────────▼─────────────────────────────┐
│                SDN Controller (Ryu)               │
│  ┌────────────────────────────────────────────┐   │
│  │         AVRO Scheduling Module             │   │
│  │  • VM Fitness Computation (Eq. 3)          │   │
│  │  • Population-Based Optimization           │   │
│  │  • Best VM Selection                       │   │
│  └────────────────────────────────────────────┘   │
│  ┌────────────────────────────────────────────┐   │
│  │         Resource Monitor Module            │   │
│  │  • OpenFlow Port Stats                     │   │
│  │  • VM CPU/Memory Polling                   │   │
│  │  • Queue Length Detection                  │   │
│  └────────────────────────────────────────────┘   │
│  ┌────────────────────────────────────────────┐   │
│  │         Flow Rule Manager                  │   │
│  │  • Path Computation                        │   │
│  │  • OpenFlow Rule Installation              │   │
│  └────────────────────────────────────────────┘   │
└─────────┬──────────────────────────────────────────┘
          │ OpenFlow 1.3
┌─────────▼──────────────────────────────────────────┐
│              Mininet Data Center Topology           │
│                                                      │
│        ┌──────┐    ┌──────┐    ┌──────┐            │
│        │ Core ├────┤ Core │    │ Core │            │
│        └──┬───┘    └──┬───┘    └──┬───┘            │
│           │           │           │                 │
│    ┌──────▼───┐ ┌─────▼────┐ ┌────▼──────┐         │
│    │ Aggr Sw  │ │ Aggr Sw  │ │ Aggr Sw   │         │
│    └──────┬───┘ └─────┬────┘ └────┬──────┘         │
│           │           │           │                 │
│    ┌──────▼───┐ ┌─────▼────┐ ┌────▼──────┐         │
│    │ Edge Sw  │ │ Edge Sw  │ │ Edge Sw   │         │
│    └──────┬───┘ └─────┬────┘ └────┬──────┘         │
│      ┌────┴───┐   ┌───┴────┐   ┌───┴────┐          │
│      │  VM1   │   │  VM2   │   │  VM3   │          │
│      │(Host1) │   │(Host2) │   │(Host3) │          │
│      └────────┘   └────────┘   └────────┘          │
└──────────────────────────────────────────────────────┘


---

## 🧮 Mathematical Model

The optimization objective minimizes a composite fitness function:

$$Z = \alpha \cdot \text{Makespan} + \beta \cdot \text{AvgResponseTime} + \gamma \cdot U_{std}$$

Where:
- **Makespan** – Total time to complete all tasks
- **AvgResponseTime** – Average per-task completion time
- **Ustd** – Standard deviation of VM utilization (load balance metric)
- **α, β, γ** – Weight parameters (tuned experimentally)

**VM Fitness Function (for AVRO selection):**

$$Fitness_{vm} = w_1(1 - CPU_{util}) + w_2(1 - Mem_{util}) + w_3\frac{1}{QueueLen+1} + w_4\frac{1}{Delay+1}$$

---

## 📁 Repository Structure

sdn-load-balancing-framework/
├── topology/
│   ├── datacenter_topo.py         # 3-tier Mininet topology
│   └── topo_config.yaml            # Topology parameters
├── controller/
│   ├── ryu_app.py                  # Main Ryu SDN controller
│   ├── flow_manager.py             # OpenFlow rule installation
│   └── packet_handler.py            # Packet-in event handling
├── scheduler/
│   ├── avro_scheduler.py           # AVRO metaheuristic implementation
│   ├── round_robin.py               # Round Robin baseline
│   ├── rf_scheduler.py              # Random Forest ML scheduler (optional)
│   └── fitness.py                   # Fitness function calculations
├── monitoring/
│   ├── resource_monitor.py          # VM CPU/Memory/Queue monitoring
│   ├── network_monitor.py           # OpenFlow port stats collector
│   └── data_logger.py                # CSV/SQLite logging
├── evaluation/
│   ├── metrics.py                    # Makespan, throughput, response time
│   ├── experiment_runner.py           # Automated experiment execution
│   └── visualization.py               # Matplotlib graphs
├── workloads/
│   ├── traffic_generator.py           # iPerf3-based traffic generation
│   ├── task_generator.py               # Synthetic task generator
│   └── workload_configs/               # YAML workload definitions
├── results/
│   ├── figures/                        # Generated plots
│   ├── logs/                            # Experiment logs
│   └── reports/                         # Analysis reports
├── tests/
│   ├── test_avro.py                     # Unit tests for AVRO
│   ├── test_monitoring.py                # Test monitoring module
│   └── test_integration.py                # End-to-end tests
├── docs/
│   ├── architecture.md                    # Detailed architecture
│   ├── api_reference.md                    # Module interfaces
│   └── experiment_design.md                 # Experiment methodology
├── requirements.txt                         # Python dependencies
├── setup.sh                                  # Environment setup script
├── CONTRIBUTING.md                            # Team contribution guidelines
├── LICENSE                                     # MIT License
└── README.md                                    # This file


---

## 🚀 Getting Started

### Prerequisites

- **Ubuntu 20.04** (or 22.04 with Mininet compatibility)
- **Python 3.8+**
- **Mininet 2.3.0**
- **Ryu SDN Controller 4.34**
- **Open vSwitch** (included with Mininet)

### Installation

1. **Clone the repository**
   git clone https://github.com/Shithijms/SDN-Cloud-Optimizer.git
   cd SDN-Cloud-Optimizer

#Run the setup script
chmod +x setup.sh
./setup.sh
Verify installation

# Test Mininet
sudo mn --test pingall

# Test Ryu
ryu-manager --version
Install Python dependencies

bash
pip install -r requirements.txt
💻 Usage
1. Start the SDN Controller
bash
# Terminal 1
ryu-manager controller/ryu_app.py
2. Launch Mininet Topology
bash
# Terminal 2
sudo python topology/datacenter_topo.py
3. Start Resource Monitoring
bash
# Terminal 3
python monitoring/resource_monitor.py --interval 2
4. Generate Workload
bash
# Terminal 4
python workloads/task_generator.py --workload medium --duration 300
5. Run Experiments
bash
# Full experiment suite
python evaluation/experiment_runner.py --algorithms avro round_robin --workloads low medium high --repeats 5

# Generate results
python evaluation/visualization.py --results-dir results/logs/
   
