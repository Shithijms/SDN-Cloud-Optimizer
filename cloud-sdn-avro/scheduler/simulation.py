"""
simulation.py
-------------
Task arrival simulation engine.

Generates realistic workload patterns:
- Uniform  : steady arrival rate
- Bursty   : quiet periods interrupted by traffic spikes
- Gravity  : heavy tasks concentrated on few sources
  (matches Traffic-1 from the AVRO paper)

This is what the workload generator (Member 1's component)
will eventually replace with real iPerf3 traffic.
"""

import random
import numpy as np


# Task size profiles — (cpu_demand, mem_demand, duration)
TASK_PROFILES = {
    'small':  {'cpu_demand': 0.10, 'mem_demand': 0.05, 'duration': 3.0},
    'medium': {'cpu_demand': 0.25, 'mem_demand': 0.15, 'duration': 8.0},
    'large':  {'cpu_demand': 0.50, 'mem_demand': 0.30, 'duration': 15.0},
    'heavy':  {'cpu_demand': 0.80, 'mem_demand': 0.50, 'duration': 25.0},
}


def generate_task(task_id: int,
                  arrival_time: float,
                  profile: str = None) -> dict:
    """
    Generate a single task.

    Parameters
    ----------
    task_id      : int
    arrival_time : float — simulation time when task arrives
    profile      : str or None — if None, randomly chosen

    Returns
    -------
    dict — task specification
    """
    if profile is None:
        # Realistic distribution — most tasks are small/medium
        profile = random.choices(
            ['small', 'medium', 'large', 'heavy'],
            weights=[50, 30, 15, 5]
        )[0]

    base = TASK_PROFILES[profile].copy()

    # Add ±20% variation to make tasks realistic
    variation = lambda x: x * random.uniform(0.8, 1.2)

    return {
        'task_id':      task_id,
        'profile':      profile,
        'cpu_demand':   float(np.clip(variation(base['cpu_demand']), 0.05, 0.95)),
        'mem_demand':   float(np.clip(variation(base['mem_demand']), 0.02, 0.95)),
        'duration':     variation(base['duration']),
        'arrival_time': arrival_time,
    }


def generate_uniform_workload(num_tasks:    int,
                               arrival_rate: float = 2.0) -> list:
    """
    Steady stream of tasks.
    arrival_rate = tasks per time unit.
    """
    tasks = []
    current_time = 0.0

    for i in range(num_tasks):
        # Inter-arrival time follows exponential distribution
        inter_arrival = random.expovariate(arrival_rate)
        current_time += inter_arrival
        tasks.append(generate_task(i, current_time))

    return tasks


def generate_bursty_workload(num_tasks:   int,
                              burst_size:  int   = 20,
                              burst_prob:  float = 0.1) -> list:
    """
    Quiet periods with sudden traffic bursts.
    Models flash crowd scenarios.
    """
    tasks        = []
    current_time = 0.0
    task_id      = 0

    while task_id < num_tasks:
        if random.random() < burst_prob:
            # Burst — many tasks arrive at once
            actual_burst = min(burst_size, num_tasks - task_id)
            for _ in range(actual_burst):
                # Tasks arrive in rapid succession during burst
                current_time += random.uniform(0.01, 0.1)
                tasks.append(generate_task(
                    task_id, current_time, profile='large'))
                task_id += 1
        else:
            # Quiet period — single task, longer gap
            current_time += random.uniform(1.0, 5.0)
            tasks.append(generate_task(task_id, current_time))
            task_id += 1

    return tasks


def generate_gravity_workload(num_tasks: int,
                               num_vms:   int = 4) -> list:
    """
    Gravity model — heavier tasks concentrate on fewer sources.
    Matches Traffic-1 from the AVRO paper.
    Some VMs receive much more traffic than others.
    """
    # Assign weights — some VMs are "hot" sources
    weights      = np.random.dirichlet(np.ones(num_vms) * 0.5)
    tasks        = []
    current_time = 0.0

    for i in range(num_tasks):
        current_time += random.expovariate(3.0)

        # Heavier load from hot sources
        source_vm = np.random.choice(num_vms, p=weights)
        profile   = 'heavy' if source_vm == np.argmax(weights) else None

        task = generate_task(i, current_time, profile)
        task['source_vm'] = int(source_vm)
        tasks.append(task)

    return tasks