"""Run reproducible AVRO fitness-weight and fast-select threshold sweeps."""

import csv
import os
import random
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))

from src.scheduler import fitness as fit
from src.scheduler.avro import AVROScheduler
from src.scheduler.environment import CloudEnvironment
from src.scheduler.simulation import (
    generate_uniform_workload,
    generate_bursty_workload,
    generate_gravity_workload,
)

RUNS = 10
WEIGHTS = {
    'baseline': (0.4, 0.3, 0.2, 0.1),
    'equal': (0.25, 0.25, 0.25, 0.25),
    'cpu-heavy': (0.6, 0.2, 0.1, 0.1),
    'net-heavy': (0.3, 0.2, 0.2, 0.3),
}
THRESHOLDS = [0.2, 0.3, 0.4]
WORKLOAD_GENERATORS = {
    'Uniform': lambda: generate_uniform_workload(200, arrival_rate=2.0),
    'Bursty': lambda: generate_bursty_workload(200, burst_size=20),
    'Gravity': lambda: generate_gravity_workload(200, num_vms=4),
}


def generate_workloads():
    """Generate each seeded workload once so all configurations share it."""
    workloads = {name: [] for name in WORKLOAD_GENERATORS}
    for seed in range(RUNS):
        for name, generator in WORKLOAD_GENERATORS.items():
            random.seed(seed)
            np.random.seed(seed)
            workloads[name].append(generator())
    return workloads


def run_configuration(name, weights, threshold, workloads):
    fit.W_CPU, fit.W_MEMORY, fit.W_QUEUE, fit.W_DELAY = weights
    response_times = []
    decision_times = []
    fast_path_count = 0
    selection_count = 0

    for workload_name, seeded_workloads in workloads.items():
        for seed, tasks in enumerate(seeded_workloads):
            random.seed(seed)
            np.random.seed(seed)
            scheduler = AVROScheduler(10, 30, threshold=threshold)
            result = CloudEnvironment(
                num_vms=4,
                seed=seed,
            ).run_experiment(tasks, scheduler, workload_name)
            response_times.append(result['avg_response'])
            decision_times.append(result['avg_decision_ms'])
            fast_path_count += scheduler.fast_path_count
            selection_count += scheduler.selection_count

    return {
        'configuration': name,
        'avg_response_mean': float(np.mean(response_times)),
        'avg_response_std': float(np.std(response_times)),
        'avg_decision_ms': float(np.mean(decision_times)),
        'fast_path_rate': (
            fast_path_count / selection_count if selection_count else 0.0
        ),
    }


def main():
    workloads = generate_workloads()
    configurations = [
        (name, weights, 0.3)
        for name, weights in WEIGHTS.items()
    ]
    configurations.extend(
        (f'thr={threshold:.1f}', WEIGHTS['baseline'], threshold)
        for threshold in THRESHOLDS
    )

    rows = [
        run_configuration(name, weights, threshold, workloads)
        for name, weights, threshold in configurations
    ]

    output_path = os.path.join(
        os.path.dirname(__file__), 'sensitivity_results.csv')
    with open(output_path, 'w', newline='', encoding='utf-8') as output:
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print('Sensitivity sweep (pooled across 3 workloads × 10 seeds)')
    print(f"{'Configuration':<14} {'Response mean±std':>22} "
          f"{'Decision ms':>13} {'Fast path':>11}")
    for row in rows:
        response = (
            f"{row['avg_response_mean']:.3f}±"
            f"{row['avg_response_std']:.3f}"
        )
        print(f"{row['configuration']:<14} {response:>22} "
              f"{row['avg_decision_ms']:>13.3f} "
              f"{row['fast_path_rate']:>10.1%}")
    print(f'\nCSV saved to: {output_path}')


if __name__ == '__main__':
    main()
