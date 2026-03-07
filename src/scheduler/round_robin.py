"""
round_robin.py
--------------
Round Robin scheduler — baseline comparison for AVRO.

Distributes tasks sequentially across VMs without considering
any real-time resource metrics. This blind distribution is the
core weakness we demonstrate AVRO overcomes.
"""

from src.scheduler.fitness import compute_fitness


class RoundRobinScheduler:

    def __init__(self, num_vms: int):
        """
        Parameters
        ----------
        num_vms : int — number of VMs to cycle through
        """
        if num_vms <= 0:
            raise ValueError("num_vms must be positive")

        self.num_vms  = num_vms
        self.current  = 0
        self.history  = []   # tracks all selections for analysis

    def select_vm(self, vm_stats_list: list = None) -> int:
        """
        Select next VM using round robin cycling.

        Deliberately ignores vm_stats_list — this blindness
        is exactly what makes Round Robin inferior to AVRO.

        Parameters
        ----------
        vm_stats_list : ignored — present only for API consistency
                        with AVROScheduler.select_vm()

        Returns
        -------
        int — next VM index in cycle
        """
        selected      = self.current
        self.current  = (self.current + 1) % self.num_vms
        self.history.append(selected)
        return selected

    def reset(self):
        """Reset cycle to beginning — useful between experiments"""
        self.current = 0
        self.history = []

    def get_distribution(self) -> dict:
        """
        Return how many times each VM was selected.
        Used by Member 4 for evaluation metrics.
        """
        return {
            i: self.history.count(i)
            for i in range(self.num_vms)
        }