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
    
    # ────────────────────────────────────────────────────────────
    # STAGE 2A — Exploration (|F| >= 1)
    # ────────────────────────────────────────────────────────────

    def _exploration(self,
                     population: np.ndarray,
                     leader_vm: int,
                     F: float,
                     num_vms: int) -> np.ndarray:
        """
        Equations 18-21 from paper — exploration stage.

        Triggered when |F| >= 1 (vulture is well-fed, searches widely).
        Two strategies selected by random vs G1:
          - Eq 19: forage around leader with exploration distance
          - Eq 21: random position within search bounds

        Parameters
        ----------
        population : np.ndarray — current VM indices
        leader_vm  : int        — VM index of leader vulture
        F          : float      — satiety value
        num_vms    : int        — total number of VMs

        Returns
        -------
        np.ndarray — updated population
        """
        new_pop = population.copy()

        for j in range(len(population)):
            rG1 = np.random.random()

            if rG1 >= G1:
                # Equation 19 — forage around leader
                X   = 2 * np.random.random()
                D_i = abs(X * leader_vm - population[j])        # Eq 20
                new_val = leader_vm - D_i * F
            else:
                # Equation 21 — random position in search space
                r3 = np.random.random()
                r4 = np.random.random()
                lb, ub = 0, num_vms - 1
                new_val = leader_vm - F + r3 * ((ub - lb) * r4 + lb)

            new_pop[j] = int(np.clip(round(new_val), 0, num_vms - 1))

        return new_pop

    # ────────────────────────────────────────────────────────────
    # STAGE 2B — Development (|F| < 1)
    # ────────────────────────────────────────────────────────────

    def _levy_flight(self, beta: float = 1.5) -> float:
        """
        Equations 33-34 from paper — Levy flight model.
        Simulates the vulture's erratic flight pattern during
        aggressive food competition.
        """
        sigma = (
            math.gamma(1 + beta) *
            math.sin(math.pi * beta / 2) /
            (math.gamma((1 + beta) / 2) * beta * 2 ** ((beta - 1) / 2))
        ) ** (1 / beta)

        u = np.random.normal(0, sigma)
        v = np.random.normal(0, 1)
        lf = 0.01 * u / (abs(v) ** (1 / beta) + 1e-10)
        return lf

    def _development(self,
                     population: np.ndarray,
                     leader_vm: int,
                     F: float,
                     num_vms: int,
                     fitness_scores: np.ndarray) -> np.ndarray:
        """
        Equations 22-32 from paper — development stage.

        Triggered when |F| < 1 (vulture is hungry, refines near leader).
        Two sub-stages based on |F| value:

        Stage One (|F| in [0.5, 1)):
          - Food competition (Eq 23) or rotating flight (Eq 27)

        Stage Two (|F| < 0.5):
          - Vulture convergence (Eq 31) or Levy flight competition (Eq 32)

        Parameters
        ----------
        population     : np.ndarray — current VM indices
        leader_vm      : int        — VM index of leader
        F              : float      — satiety value
        num_vms        : int        — total VMs available
        fitness_scores : np.ndarray — current fitness of each member

        Returns
        -------
        np.ndarray — updated population
        """
        new_pop = population.copy()
        sorted_idx = np.argsort(fitness_scores)[::-1]

        # Best1 and Best2 VM indices for convergence equations
        best1_vm = int(population[sorted_idx[0]])
        best2_vm = int(population[sorted_idx[1]]) if len(sorted_idx) > 1 else best1_vm

        for j in range(len(population)):
            abs_F = abs(F)

            if abs_F >= 0.5:
                # ── Development Stage One ──────────────────────
                rG2 = np.random.random()

                if rG2 >= G2:
                    # Food competition — Equation 23
                    r5    = np.random.random()
                    d_t   = leader_vm - population[j]           # Eq 24
                    new_val = abs_F * (F + r5) - d_t

                else:
                    # Rotating flight — Equations 25, 26, 27
                    r6 = np.random.random()
                    r7 = np.random.random()
                    p  = population[j] + 1e-10                  # avoid div by zero

                    S1 = leader_vm * (r6 * p / (2 * math.pi)) * math.cos(p)
                    S2 = leader_vm * (r7 * p / (2 * math.pi)) * math.sin(p)
                    new_val = leader_vm - (S1 + S2)

            else:
                # ── Development Stage Two ──────────────────────
                rG3 = np.random.random()

                if rG3 >= G3:
                    # Vulture convergence — Equations 29, 30, 31
                    denom1 = (best1_vm - population[j] ** 2) + 1e-10
                    denom2 = (best2_vm - population[j] ** 2) + 1e-10

                    A1 = best1_vm - (best1_vm * population[j]) / denom1 * F
                    A2 = best2_vm - (best2_vm * population[j]) / denom2 * F

                    new_val = (A1 + A2) / 2                     # Eq 31

                else:
                    # Levy flight food competition — Equation 32
                    d_t   = leader_vm - population[j]
                    lf    = self._levy_flight()
                    new_val = leader_vm - abs(d_t) * F * lf

            new_pop[j] = int(np.clip(round(new_val), 0, num_vms - 1))

        return new_pop

    # ────────────────────────────────────────────────────────────
    # STAGE 3 — Full Optimization Loop
    # ────────────────────────────────────────────────────────────

    def select_vm(self,
                  vm_stats_list: list,
                  track_convergence: bool = False):
        """
        Main entry point — runs full AVRO optimization loop.

        Iterates through exploration, development, and optimization
        stages to find the best VM for an incoming task.

        Parameters
        ----------
        vm_stats_list    : list of dicts — real-time stats per VM
        track_convergence: bool — if True, returns convergence history
                           for plotting (used in evaluation/report)

        Returns
        -------
        If track_convergence is False:
            int — index of best VM selected

        If track_convergence is True:
            tuple: (int, list)
                int  — index of best VM selected
                list — best fitness score at each iteration
        """
        num_vms = len(vm_stats_list)

        if num_vms == 0:
            raise ValueError("vm_stats_list cannot be empty")
        if num_vms == 1:
            return (0, []) if track_convergence else 0

        # Step 1 — Initialize population
        population     = self.initialize_population(num_vms)
        fitness_scores = self.compute_population_fitness(
            population, vm_stats_list)

        convergence_history = []
        best_vm_overall     = int(population[np.argmax(fitness_scores)])
        best_fitness_overall = np.max(fitness_scores)

        # Step 2 — Iterate
        for i in range(self.max_iter):

            # Step 2a — Select leader vulture
            leader_vm = self.select_leader(population, fitness_scores)

            # Step 2b — Compute satiety F
            F = self.compute_satiety(i)

            # Step 2c — Update population based on |F|
            if abs(F) >= 1:
                population = self._exploration(
                    population, leader_vm, F, num_vms)
            else:
                population = self._development(
                    population, leader_vm, F, num_vms, fitness_scores)

            # Step 2d — Recompute fitness after update
            fitness_scores = self.compute_population_fitness(
                population, vm_stats_list)

            # Step 2e — Track best solution found so far
            current_best_fitness = np.max(fitness_scores)
            current_best_vm      = int(
                population[np.argmax(fitness_scores)])

            if current_best_fitness > best_fitness_overall:
                best_fitness_overall = current_best_fitness
                best_vm_overall      = current_best_vm

            if track_convergence:
                convergence_history.append(round(best_fitness_overall, 6))

        if track_convergence:
            return best_vm_overall, convergence_history
        return best_vm_overall
    