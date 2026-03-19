"""
run_experiment.py
-----------------
Runs full dynamic simulation comparing AVRO vs Round Robin.
Uses realistic workload patterns and dynamic VM state.

Run: python results/run_experiment.py
"""

import sys
import os
import matplotlib
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for plotting
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))

from src.scheduler.avro        import AVROScheduler
from src.scheduler.round_robin import RoundRobinScheduler
from src.scheduler.environment import CloudEnvironment
from src.scheduler.simulation  import (generate_uniform_workload,
                                        generate_bursty_workload,
                                        generate_gravity_workload)
from src.scheduler.baselines import LeastLoadedScheduler, WeightedRoundRobinScheduler, FCFS_Scheduler
from src.scheduler.round_robin import RoundRobinScheduler
from src.scheduler.fitness     import compute_fitness

VM_CAPACITIES = [2,4,4,8]


WORKLOADS = {
    'Uniform':  generate_uniform_workload(200, arrival_rate=2.0),
    'Bursty':   generate_bursty_workload(200,  burst_size=20),
    'Gravity':  generate_gravity_workload(200,  num_vms=4),
}


from src.scheduler.baselines   import (LeastLoadedScheduler,
                                        WeightedRoundRobinScheduler,
                                        FCFS_Scheduler)
from src.scheduler.round_robin import RoundRobinScheduler


VM_CAPACITIES = [2, 4, 4, 8]  # cpu_cores matching CloudEnvironment

NUM_EXPERIMENT_RUNS = 5  # run each experiment 5 times, report mean

def run_averaged_experiments():
    """Run each workload/scheduler combination multiple times"""
    all_results = {w: {s: [] for s in [
        'AVRO', 'LeastLoaded', 'WeightedRR', 'FCFS', 'RoundRobin'
    ]} for w in WORKLOADS}

    for run in range(NUM_EXPERIMENT_RUNS):
        print(f"\n  Run {run+1}/{NUM_EXPERIMENT_RUNS}")
        # Regenerate workloads each run for variance
        workloads = {
            'Uniform': generate_uniform_workload(200, arrival_rate=2.0),
            'Bursty':  generate_bursty_workload(200, burst_size=20),
            'Gravity': generate_gravity_workload(200, num_vms=4),
        }

        for workload_name, tasks in workloads.items():
            schedulers = {
                'AVRO':        AVROScheduler(pop_size=10, max_iter=30),
                'LeastLoaded': LeastLoadedScheduler(),
                'WeightedRR':  WeightedRoundRobinScheduler(VM_CAPACITIES),
                'FCFS':        FCFS_Scheduler(),
                'RoundRobin':  RoundRobinScheduler(num_vms=4),
            }

            for sched_name, scheduler in schedulers.items():
                env    = CloudEnvironment(num_vms=4, seed=run)
                result = env.run_experiment(
                    tasks, scheduler, sched_name)
                all_results[workload_name][sched_name].append(result)

    # Average across runs
    averaged = {}
    metrics_to_avg = [
        'avg_fitness', 'avg_response', 'makespan',
        'throughput', 'weighted_dev', 'decision_quality'
    ]

    for workload_name in all_results:
        averaged[workload_name] = {}
        for sched_name in all_results[workload_name]:
            runs  = all_results[workload_name][sched_name]
            entry = {}
            for m in metrics_to_avg:
                vals       = [r[m] for r in runs]
                entry[m]   = round(np.mean(vals), 4)
                entry[f'{m}_std'] = round(np.std(vals), 4)
            # Keep vm_distribution from last run
            entry['vm_distribution']  = runs[-1]['vm_distribution']
            entry['avg_decision_ms']  = round(np.mean(
                [r['avg_decision_ms'] for r in runs]), 4)
            averaged[workload_name][sched_name] = entry

    return averaged

def run_all_experiments():
    results = {}

    for workload_name, tasks in WORKLOADS.items():
        print(f"\n  Running: {workload_name} workload ({len(tasks)} tasks)")

        schedulers = {
            'AVRO': AVROScheduler(pop_size=10, max_iter=30),
            'LeastLoaded': LeastLoadedScheduler(),
            'WeightedRR':  WeightedRoundRobinScheduler(VM_CAPACITIES),
            'FCFS':        FCFS_Scheduler(),
            'RoundRobin':  RoundRobinScheduler(num_vms=4),
        }

        workload_results = {}

        for sched_name, scheduler in schedulers.items():
            env    = CloudEnvironment(num_vms=4, seed=42)
            result = env.run_experiment(tasks, scheduler, sched_name)
            workload_results[sched_name] = result

            print(f"    {sched_name:<14} "
                  f"fitness={result['avg_fitness']:.4f}  "
                  f"response={result['avg_response']:.2f}  "
                  f"makespan={result['makespan']:.1f}")

        results[workload_name] = workload_results

    return results

def print_results_table(results):
    print("\n" + "="*85)
    print("  FULL COMPARISON — AVRO vs ALL BASELINES")
    print("="*85)

    metrics_to_show = [
        ('avg_fitness',   'Avg Fitness',       'higher'),
        ('avg_response',  'Avg Response Time', 'lower'),
        ('makespan',      'Makespan',          'lower'),
        ('throughput',    'Throughput',        'higher'),
        ('weighted_dev',  'Weighted Load Dev', 'lower'),
        ('decision_quality','Decision Quality','higher'),
    ]

    sched_order = ['AVRO', 'LeastLoaded', 'WeightedRR', 'FCFS', 'RoundRobin']

    for workload_name, res in results.items():
        print(f"\n  Workload: {workload_name}")
        print(f"  {'Metric':<22} " +
              " ".join(f"{s:>12}" for s in sched_order))
        print("  " + "-"*82)

        printed_metrics = set()
        for metric_key, metric_label, direction in metrics_to_show:
            if metric_key in printed_metrics:
                continue
            printed_metrics.add(metric_key)

            values = [res[s][metric_key] for s in sched_order]
            best   = min(values) if direction == 'lower' else max(values)

            row = f"  {metric_label:<22}"
            for i, (s, v) in enumerate(zip(sched_order, values)):
                # Mark best value with arrow
                marker = " ←" if abs(v - best) < 1e-6 else "  "
                row   += f"{v:>11.4f}{marker}"[0:13]

            print(row)

        # VM distribution row
        print(f"  {'VM Distribution':<22}", end="")
        for s in sched_order:
            dist = res[s]['vm_distribution']
            d    = "/".join(str(dist[i]) for i in range(4))
            print(f" {d:>12}", end="")
        print()

        # AVRO improvement over each baseline
        print(f"\n  AVRO improvement over baselines ({workload_name}):")
        avro_fitness = res['AVRO']['avg_fitness']
        avro_resp    = res['AVRO']['avg_response']

        for s in sched_order[1:]:
            fit_imp  = (avro_fitness - res[s]['avg_fitness']) / res[s]['avg_fitness'] * 100
            resp_imp = (res[s]['avg_response'] - avro_resp) / res[s]['avg_response'] * 100
            print(f"    vs {s:<14} fitness: {fit_imp:>+6.1f}%  "
                  f"response time: {resp_imp:>+6.1f}%")

        print("  " + "="*82)

def plot_dynamic_results(results):
    sched_order  = ['AVRO', 'LeastLoaded', 'WeightedRR', 'FCFS', 'RoundRobin']
    colors       = {
        'AVRO':        '#1976d2',
        'LeastLoaded': '#388e3c',
        'WeightedRR':  '#f57c00',
        'FCFS':        '#7b1fa2',
        'RoundRobin':  '#d32f2f',
    }
    workloads    = list(results.keys())

    fig, axes = plt.subplots(3, 3, figsize=(18, 14))
    fig.suptitle(
        'AVRO vs All Baselines — Full Comparison\n'
        'Dynamic Simulation with Realistic Workloads',
        fontsize=14, fontweight='bold')

    metrics = [
        ('avg_fitness',  'Avg Fitness Score'),
        ('avg_response', 'Avg Response Time'),
        ('weighted_dev', 'Weighted Load Dev\n(lower=better)'),
    ]

    for row, (metric_key, metric_label) in enumerate(metrics):
        for col, workload_name in enumerate(workloads):
            ax  = axes[row][col]
            res = results[workload_name]

            values = [res[s][metric_key] for s in sched_order]
            bars   = ax.bar(
                range(len(sched_order)),
                values,
                color=[colors[s] for s in sched_order],
                alpha=0.85,
                edgecolor='white'
            )

            # Highlight AVRO bar
            bars[0].set_edgecolor('black')
            bars[0].set_linewidth(2)

            # Value labels
            for bar, val in zip(bars, values):
                ax.text(bar.get_x() + bar.get_width()/2,
                        bar.get_height() + max(values)*0.01,
                        f'{val:.3f}',
                        ha='center', va='bottom',
                        fontsize=7, fontweight='bold')

            if row == 0:
                ax.set_title(f'{workload_name}', fontsize=11)
            if col == 0:
                ax.set_ylabel(metric_label, fontsize=9)

            ax.set_xticks(range(len(sched_order)))
            ax.set_xticklabels(
                ['AVRO', 'LL', 'WRR', 'FCFS', 'RR'],
                fontsize=8)
            ax.grid(True, alpha=0.3, axis='y')
            ax.set_ylim(0, max(values) * 1.25)

    plt.tight_layout()
    output_path = os.path.join(
        os.path.dirname(__file__), 'full_comparison.png')
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"\n  Saved: {output_path}")


def main():
    print("\n" + "="*85)
    print(f"  FULL COMPARISON — AVRO vs ALL BASELINES ({NUM_EXPERIMENT_RUNS} runs each)")
    print("="*85)

    results = run_averaged_experiments()
    print_results_table(results)
    plot_dynamic_results(results)
    print(f"\n  Done. Results averaged over {NUM_EXPERIMENT_RUNS} runs.")


if __name__ == "__main__":
    main()