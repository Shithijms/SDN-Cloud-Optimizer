"""
avro.py
-------
African Vulture Routing Optimization (AVRO) adapted for VM selection.

Original paper: Chen et al. (2024) - Dynamic routing optimization in
software-defined networking based on a metaheuristic algorithm.

Adaptation: Instead of optimizing link weights, this implementation
optimizes VM selection for task scheduling in SDN-cloud environments.

Population  = set of candidate VM index assignments (integers)
Fitness     = how suitable a VM is (from fitness.py)
Leader      = VM index with highest fitness in current population
"""

import numpy as np
import math
from src.scheduler.fitness import compute_fitness, rank_vms


# ── Algorithm parameters (Table 3 from paper) ──────────────────
POP_SIZE   = 10       # population size
MAX_ITER   = 100      # maximum iterations
T_TRAIN    = 70       # iteration when optimization stage starts
GAMMA      = 2        # controls satiety baseline (Eq. 16)
DELTA2     = 0.0001   # limits F range in optimization stage (Eq. 36)
G1         = 0.4      # exploration method selector (Eq. 18)
G2         = 0.3      # development stage 1 selector (Eq. 22)
G3         = 0.4      # development stage 2 selector (Eq. 28)
L1         = 0.6      # probability of selecting Best1 as leader
L2         = 0.4      # probability of selecting Best2 as leader


class AVROScheduler:

    def __init__(self,
                 pop_size=POP_SIZE,
                 max_iter=MAX_ITER,
                 t_train=T_TRAIN):
        self.pop_size = pop_size
        self.max_iter = max_iter
        self.t_train  = t_train

    # ────────────────────────────────────────────────────────────
    # STAGE 1A — Population Initialization
    # ────────────────────────────────────────────────────────────

    def initialize_population(self, num_vms: int) -> np.ndarray:
        """
        Equation 12 from paper — random initialization.

        Each element is a VM index (integer 0 to num_vms-1).
        Population size = self.pop_size candidate solutions.

        Parameters
        ----------
        num_vms : int — number of available VMs

        Returns
        -------
        np.ndarray of shape (pop_size,) with integer VM indices
        """
        population = np.random.randint(0, num_vms, self.pop_size)
        return population

    def compute_population_fitness(self,
                                   population: np.ndarray,
                                   vm_stats_list: list) -> np.ndarray:
        """
        Compute fitness for every member of the population.

        Parameters
        ----------
        population     : np.ndarray — array of VM indices
        vm_stats_list  : list of dicts — real-time stats per VM

        Returns
        -------
        np.ndarray of fitness scores, same length as population
        """
        num_vms = len(vm_stats_list)
        fitness_scores = np.zeros(self.pop_size)

        for j, vm_idx in enumerate(population):
            vm_idx = int(np.clip(vm_idx, 0, num_vms - 1))
            fitness_scores[j] = compute_fitness(vm_stats_list[vm_idx])

        return fitness_scores

    # ────────────────────────────────────────────────────────────
    # STAGE 1B — Leader Selection
    # ────────────────────────────────────────────────────────────

    def select_leader(self,
                      population: np.ndarray,
                      fitness_scores: np.ndarray) -> int:
        """
        Equation 14 from paper — select leader vulture.

        Identifies Best1 and Best2 (highest fitness members).
        Uses roulette wheel to pick one as the leader.

        Parameters
        ----------
        population     : np.ndarray — current VM index population
        fitness_scores : np.ndarray — fitness of each population member

        Returns
        -------
        int — VM index of the selected leader
        """
        sorted_indices = np.argsort(fitness_scores)[::-1]
        best1_pos = sorted_indices[0]
        best2_pos = sorted_indices[1] if len(sorted_indices) > 1 else sorted_indices[0]

        best1_vm = int(population[best1_pos])
        best2_vm = int(population[best2_pos])

        # Roulette wheel selection (Equation 15)
        r = np.random.random()
        leader_vm = best1_vm if r < L1 else best2_vm

        return leader_vm

    # ────────────────────────────────────────────────────────────
    # STAGE 1C — Satiety Computation
    # ────────────────────────────────────────────────────────────

    def compute_satiety(self, iteration: int) -> float:
        """
        Equations 16 and 17 from paper — vulture satiety F.

        F controls exploration vs development:
          |F| >= 1  →  exploration  (search widely)
          |F| <  1  →  development  (refine near leader)

        In optimization stage (iteration >= t_train):
          F is clipped to [-delta2, delta2] for stable convergence.

        Parameters
        ----------
        iteration : int — current iteration number

        Returns
        -------
        float — satiety value F
        """
        h  = np.random.uniform(-2, 2)
        z  = np.random.uniform(-1, 1)
        r2 = np.random.random()

        # Equation 16
        t = h * (
            math.sin(math.pi / 2 * iteration / self.max_iter) ** GAMMA +
            math.cos(math.pi  * iteration / self.max_iter) - 1
        )

        if iteration < self.t_train:
            # Equation 17 — normal satiety
            F = (2 * r2 + 1) * z * (1 - iteration / self.t_train) + t
        else:
            # Equation 35 — optimization stage satiety
            F = (2 * r2 + 1) * z * (1 - iteration / self.t_train) + t
            # Equation 36 — clip to stable range
            F = float(np.clip(F, -DELTA2, DELTA2))

        return F
    