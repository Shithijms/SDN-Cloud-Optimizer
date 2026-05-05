"""
vm_state.py
-----------
Dynamic VM state manager.

Simulates realistic VM behavior where:
- Incoming tasks increase CPU and memory load
- Tasks complete over time, freeing resources
- Queue builds up when VM is busy
- Network delay increases under heavy load

This replaces the static hardcoded VM stats dicts.
In Month 2, real stats will come from Mininet hosts.
For now this gives us realistic dynamic behavior to test against.
"""

import time
import random
import numpy as np


class VMState:
    """
    Represents a single VM with dynamic resource state.

    Resource model:
    - Each task consumes a slice of CPU and memory
    - Tasks have a duration — they complete and free resources
    - Queue builds when all CPU is busy
    - Delay increases linearly with queue length
    """

    def __init__(self,
                 vm_id:       int,
                 cpu_cores:   int   = 4,
                 memory_gb:   float = 8.0,
                 base_delay:  float = 5.0,
                 cpu_noise:   float = 0.02):
        """
        Parameters
        ----------
        vm_id      : int   — unique identifier
        cpu_cores  : int   — number of CPU cores (affects capacity)
        memory_gb  : float — total RAM in GB
        base_delay : float — baseline network delay in ms
        cpu_noise  : float — random CPU fluctuation (simulates OS noise)
        """
        self.vm_id      = vm_id
        self.cpu_cores  = cpu_cores
        self.memory_gb  = memory_gb
        self.base_delay = base_delay
        self.cpu_noise  = cpu_noise

        # Active tasks: list of dicts with remaining_time, cpu_use, mem_use
        self.active_tasks = []

        # Cumulative stats for evaluation
        self.total_tasks_received  = 0
        self.total_tasks_completed = 0
        self.total_wait_time       = 0.0

    # ── Resource calculation ─────────────────────────────────────

    @property
    def cpu(self) -> float:
        """Current CPU utilization [0.0, 1.0]"""
        base = sum(t['cpu_use'] for t in self.active_tasks)
        noise = random.gauss(0, self.cpu_noise)
        return float(np.clip(base + noise, 0.0, 1.0))

    @property
    def memory(self) -> float:
        """Current memory utilization [0.0, 1.0]"""
        used_gb = sum(t['mem_use'] * self.memory_gb
                      for t in self.active_tasks)
        return float(np.clip(used_gb / self.memory_gb, 0.0, 1.0))

    @property
    def queue_length(self) -> int:
        """Number of tasks currently active"""
        return len(self.active_tasks)

    @property
    def delay(self) -> float:
        """
        Network delay increases with queue length.
        Models head-of-line blocking under load.
        """
        congestion_penalty = self.queue_length * 3.0
        return self.base_delay + congestion_penalty

    def get_stats(self) -> dict:
        """
        Return current state in the standard VM_STATS format.
        This is what AVROScheduler.select_vm() expects.
        """
        return {
            'vm_id':        self.vm_id,
            'cpu':          self.cpu,
            'memory':       self.memory,
            'queue_length': self.queue_length,
            'delay':        self.delay,
            'timestamp':    time.time(),
        }

    # ── Task lifecycle ───────────────────────────────────────────

    def assign_task(self, task: dict):
        """
        Assign an incoming task to this VM.

        Parameters
        ----------
        task : dict with keys:
            task_id      : int
            cpu_demand   : float — fraction of CPU needed [0.0, 1.0]
            mem_demand   : float — fraction of memory needed [0.0, 1.0]
            duration     : float — how long task runs (seconds/ticks)
            arrival_time : float — when task was submitted
        """
        self.active_tasks.append({
            'task_id':        task['task_id'],
            'cpu_use':        task['cpu_demand'] / self.cpu_cores,
            'mem_use':        task['mem_demand'],
            'remaining_time': task['duration'],
            'arrival_time':   task['arrival_time'],
        })
        self.total_tasks_received += 1

    def tick(self, dt: float = 1.0):
        """
        Advance simulation time by dt units.
        Stronger VMs process tasks faster.
        cpu_cores acts as a speed multiplier.
        """
        completed = []

        # Stronger VMs process faster — this is what makes
        # VM selection matter for makespan
        effective_dt = dt * (self.cpu_cores / 2.0)

        for task in self.active_tasks:
            task['remaining_time'] -= effective_dt

        just_finished = [
            t for t in self.active_tasks
            if t['remaining_time'] <= 0
        ]

        for task in just_finished:
            self.active_tasks.remove(task)
            self.total_tasks_completed += 1
            completed.append(task['task_id'])

        return completed

    def is_overloaded(self, cpu_threshold=0.85) -> bool:
        """True if VM is under heavy load"""
        return self.cpu > cpu_threshold

    def __repr__(self):
        return (f"VM{self.vm_id}("
                f"cpu={self.cpu:.2f}, "
                f"mem={self.memory:.2f}, "
                f"queue={self.queue_length}, "
                f"delay={self.delay:.1f}ms)")