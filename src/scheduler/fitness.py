"""
fitness.py
----------
VM fitness function for AVRO-based task scheduler.

Fitness measures how suitable a VM is for receiving a new task.
Higher fitness = better candidate.

Input:  VM state dict {cpu, memory, queue_length, delay}
Output: float in range (0, 1]
"""


# Weight constants — how much each metric contributes to fitness
# These match your synopsis Equation 3 priority ordering:
# CPU is most critical, then memory, then queue, then delay
W_CPU    = 0.4
W_MEMORY = 0.3
W_QUEUE  = 0.2
W_DELAY  = 0.1


def compute_fitness(vm_stats: dict) -> float:
    """
    Compute fitness score for a single VM.

    Parameters
    ----------
    vm_stats : dict
        cpu          : float  — CPU utilization, range [0.0, 1.0]
        memory       : float  — Memory utilization, range [0.0, 1.0]
        queue_length : int    — Number of tasks waiting in queue
        delay        : float  — Network delay in milliseconds

    Returns
    -------
    float
        Fitness score. Higher is better.
        A VM with cpu=0, memory=0, queue=0, delay=0 scores 1.0 (perfect).
        A VM with cpu=1, memory=1, queue=inf, delay=inf scores near 0.
    """

    cpu_score    = 1.0 - vm_stats['cpu']
    mem_score    = 1.0 - vm_stats['memory']
    queue_score  = 1.0 / (vm_stats['queue_length'] + 1)
    delay_score  = 1.0 / (vm_stats['delay'] + 1)

    fitness = (W_CPU    * cpu_score   +
               W_MEMORY * mem_score   +
               W_QUEUE  * queue_score +
               W_DELAY  * delay_score)

    return round(fitness, 6)


def rank_vms(vm_stats_list: list) -> list:
    """
    Rank a list of VMs by fitness score, best first.

    Parameters
    ----------
    vm_stats_list : list of dicts
        Each dict follows the vm_stats format above.

    Returns
    -------
    list of tuples: [(vm_index, fitness_score), ...]
        Sorted descending by fitness score.
    """
    scored = [
        (idx, compute_fitness(vm))
        for idx, vm in enumerate(vm_stats_list)
    ]
    return sorted(scored, key=lambda x: x[1], reverse=True)

def compute_relative_fitness(vm_stats_list: list) -> list:
    """
    Compute fitness scores relative to the current pool.

    When all VMs are overloaded, absolute fitness scores are all
    near zero and AVRO can't differentiate. Relative scoring
    finds the least-bad option even in saturated conditions.

    Returns list of (vm_index, relative_fitness) sorted best first.
    """
    raw_scores = [
        (i, compute_fitness(vm))
        for i, vm in enumerate(vm_stats_list)
    ]

    scores_only = [s for _, s in raw_scores]
    min_s = min(scores_only)
    max_s = max(scores_only)
    score_range = max_s - min_s

    if score_range < 0.01:
        # All VMs nearly identical — use CPU as tiebreaker
        return sorted(
            [(i, 1.0 - vm['cpu']) for i, vm in enumerate(vm_stats_list)],
            key=lambda x: x[1],
            reverse=True
        )

    # Normalize to [0, 1] within current pool
    normalized = [
        (i, (s - min_s) / score_range)
        for i, s in raw_scores
    ]
    return sorted(normalized, key=lambda x: x[1], reverse=True)
