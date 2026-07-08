"""
run_experiment.py
-----------------
Runs full dynamic simulation comparing AVRO vs Round Robin.
Uses realistic workload patterns and dynamic VM state.

Run: python results/run_experiment.py
"""

import sys
import os
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for plotting
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))

from src.scheduler.avro        import AVROScheduler
from src.scheduler.environment import CloudEnvironment
from src.scheduler.simulation  import (generate_uniform_workload,
                                        generate_bursty_workload,
                                        generate_gravity_workload)
from src.scheduler.baselines   import (LeastLoadedScheduler,
                                        WeightedRoundRobinScheduler,
                                        FCFS_Scheduler)
from src.scheduler.round_robin import RoundRobinScheduler
from src.scheduler.fitness     import compute_fitness

VM_CAPACITIES = [2, 4, 4, 8]  # cpu_cores matching CloudEnvironment
NUM_EXPERIMENT_RUNS = 5  # run each experiment 5 times, report mean

WORKLOADS = {
    'Uniform':  generate_uniform_workload(200, arrival_rate=2.0),
    'Bursty':   generate_bursty_workload(200,  burst_size=20),
    'Gravity':  generate_gravity_workload(200,  num_vms=4),
}


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
# --- Added block to print std devs ---
            print(f"\n  Std deviations ({workload_name}):")
            for metric_key, metric_label, _ in metrics_to_show:
                print(f"  {metric_label:<22}", end="")
                for s in sched_order:
                    std = results[workload_name][s].get(f'{metric_key}_std', 0)
                    print(f" {std:>12.4f}", end="")
                print()
        # --------------------------------------
        # VM distribution row
        print(f"  {'VM Distribution':<22}", end="")
        for s in sched_order:
            dist = res[s]['vm_distribution']
            d    = "/".join(str(dist[i]) for i in range(4))
            print(f" {d:>12}", end="")
        print()

    # --- NEW: Explicit Format for Paper (Table I) ---
    print("\n" + "="*85)
    print("  TABLE I: DECISION QUALITY (DQ) COMPARISON ACROSS WORKLOAD PROFILES")
    print("="*85)
    print(f"  {'Algorithm':<18} | {'Uniform':<10} | {'Bursty':<10} | {'Gravity':<10}")
    print("  " + "-"*65)
    
    # Matching exact order and names from the research paper draft
    table_order = ['AVRO', 'FCFS', 'LeastLoaded', 'RoundRobin', 'WeightedRR']
    labels = {
        'AVRO': 'AVRO (proposed)',
        'FCFS': 'FCFS',
        'LeastLoaded': 'Least Loaded',
        'RoundRobin': 'Round Robin',
        'WeightedRR': 'Weighted RR'
    }
    
    for s in table_order:
        u_dq = results['Uniform'][s]['decision_quality']
        b_dq = results['Bursty'][s]['decision_quality']
        g_dq = results['Gravity'][s]['decision_quality']
        print(f"  {labels[s]:<18} | {u_dq:<10.4f} | {b_dq:<10.4f} | {g_dq:<10.4f}")

    # --- NEW: Explicit Format for Paper (Section IV-D % Improvements) ---
    print("\n" + "="*85)
    print("  SECTION IV-D: EXACT % IMPROVEMENTS (AVRO vs Round Robin)")
    print("="*85)
    for wl in ['Uniform', 'Bursty', 'Gravity']:
        rr_resp = results[wl]['RoundRobin']['avg_response']
        avro_resp = results[wl]['AVRO']['avg_response']
        resp_imp = ((rr_resp - avro_resp) / rr_resp) * 100
        
        rr_fit = results[wl]['RoundRobin']['avg_fitness']
        avro_fit = results[wl]['AVRO']['avg_fitness']
        fit_imp = ((avro_fit - rr_fit) / rr_fit) * 100
        
        print(f"  {wl:<10} Workload -> Response Time Improv: {resp_imp:>5.2f}% | Fitness Improv: {fit_imp:>5.2f}%")
    print("  " + "="*85)


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