"""
baselines.py
------------
Traditional scheduling baselines for comparison against AVRO.

These represent the state-of-practice before intelligent
scheduling. AVRO must outperform all of these to make a
credible contribution claim.

Algorithms:
1. Round Robin         — blind sequential cycling
2. Least Loaded        — greedy CPU-based selection  
3. Weighted Round Robin — capacity-aware cycling
4. FCFS                — shortest queue first
"""

import numpy as np
from src.scheduler.fitness import compute_fitness


# ── 1. Least Loaded ─────────────────────────────────────────────

class LeastLoadedScheduler:
    """
    Selects VM with lowest current CPU utilization.

    This is the strongest traditional baseline — it uses
    real-time information but only considers one metric (CPU).
    AVRO must beat this to prove multi-metric optimization matters.
    """

    def __init__(self):
        self.history = []

    def select_vm(self, vm_stats_list: list) -> int:
        selected = min(
            range(len(vm_stats_list)),
            key=lambda i: vm_stats_list[i]['cpu']
        )
        self.history.append(selected)
        return selected

    def reset(self):
        self.history = []


# ── 2. Weighted Round Robin ──────────────────────────────────────

class WeightedRoundRobinScheduler:
    """
    Distributes tasks proportional to VM capacity.

    Stronger VMs receive more tasks. Better than plain RR
    because it accounts for heterogeneous hardware.
    Still blind to real-time load — uses only static weights.
    """

    def __init__(self, vm_capacities: list):
        """
        Parameters
        ----------
        vm_capacities : list of int — cpu_cores per VM
                        e.g. [2, 4, 4, 8] for our 4-VM setup
        """
        self.vm_capacities = vm_capacities
        total = sum(vm_capacities)

        # Build weighted sequence
        # VM with 8 cores appears 4x more than VM with 2 cores
        self.sequence = []
        for vm_id, cores in enumerate(vm_capacities):
            self.sequence.extend([vm_id] * cores)

        self.current  = 0
        self.history  = []

    def select_vm(self, vm_stats_list: list = None) -> int:
        selected      = self.sequence[self.current]
        self.current  = (self.current + 1) % len(self.sequence)
        self.history.append(selected)
        return selected

    def reset(self):
        self.current = 0
        self.history = []

    def get_distribution(self) -> dict:
        return {
            i: self.history.count(i)
            for i in range(len(self.vm_capacities))
        }


# ── 3. FCFS — Shortest Queue First ──────────────────────────────

class FCFS_Scheduler:
    """
    First Come First Served — assigns to VM with shortest queue.

    Models traditional FCFS behavior where tasks go to the
    first available server. Considers queue length but ignores
    CPU, memory, and network delay.
    """

    def __init__(self):
        self.history = []

    def select_vm(self, vm_stats_list: list) -> int:
        selected = min(
            range(len(vm_stats_list)),
            key=lambda i: vm_stats_list[i]['queue_length']
        )
        self.history.append(selected)
        return selected

    def reset(self):
        self.history = []


# ── 4. Round Robin (kept for reference) ─────────────────────────

class RoundRobinScheduler:
    """Imported from round_robin.py — kept here for convenience"""
    pass