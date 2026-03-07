"""
plot_convergence.py
-------------------
Generates convergence and comparison plots for the report.
Run from project root: python results/plot_convergence.py
"""

import sys
import os
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for environments without display
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))

from src.scheduler.avro        import AVROScheduler
from src.scheduler.round_robin import RoundRobinScheduler
from src.scheduler.fitness     import compute_fitness


# ── VM scenarios ────────────────────────────────────────────────
VM_STATS = [
    {'cpu': 0.95, 'memory': 0.90, 'queue_length': 10, 'delay': 30.0},
    {'cpu': 0.30, 'memory': 0.40, 'queue_length': 1,  'delay': 8.0},
    {'cpu': 0.60, 'memory': 0.55, 'queue_length': 3,  'delay': 15.0},
    {'cpu': 0.20, 'memory': 0.30, 'queue_length': 0,  'delay': 5.0},
]

VM_LABELS = [
    'VM0\n(Overloaded)',
    'VM1\n(Healthy)',
    'VM2\n(Moderate)',
    'VM3\n(Best)',
]


def plot_convergence(ax, num_runs=10):
    """
    Plot 1 — AVRO convergence curves over multiple runs.
    Shows algorithm stability.
    """
    scheduler = AVROScheduler(pop_size=10, max_iter=100)
    all_histories = []

    for _ in range(num_runs):
        _, history = scheduler.select_vm(
            VM_STATS, track_convergence=True)
        all_histories.append(history)

    history_array = np.array(all_histories)
    mean_history  = history_array.mean(axis=0)
    std_history   = history_array.std(axis=0)
    iterations    = range(1, 101)

    # Plot individual runs faintly
    for h in all_histories:
        ax.plot(iterations, h, alpha=0.15, color='steelblue', linewidth=0.8)

    # Plot mean with confidence band
    ax.plot(iterations, mean_history,
            color='steelblue', linewidth=2.5,
            label=f'AVRO Mean (n={num_runs})')
    ax.fill_between(iterations,
                    mean_history - std_history,
                    mean_history + std_history,
                    alpha=0.2, color='steelblue',
                    label='±1 std dev')

    ax.axhline(y=max(compute_fitness(vm) for vm in VM_STATS),
               color='green', linestyle='--', linewidth=1.5,
               label='Optimal fitness (VM3)')

    ax.set_xlabel('Iteration', fontsize=11)
    ax.set_ylabel('Best Fitness Score', fontsize=11)
    ax.set_title('AVRO Convergence Across Multiple Runs', fontsize=13)
    ax.legend(fontsize=9)
    ax.set_ylim(0, 1.05)
    ax.grid(True, alpha=0.3)


def plot_vm_selection_distribution(ax, num_tasks=200):
    """
    Plot 2 — VM selection distribution: AVRO vs Round Robin.
    Shows AVRO intelligence vs RR blindness.
    """
    avro = AVROScheduler(pop_size=10, max_iter=100)
    rr   = RoundRobinScheduler(num_vms=4)

    avro_counts = {i: 0 for i in range(4)}
    rr_counts   = {i: 0 for i in range(4)}

    for _ in range(num_tasks):
        avro_vm = avro.select_vm(VM_STATS)
        rr_vm   = rr.select_vm(VM_STATS)
        avro_counts[avro_vm] += 1
        rr_counts[rr_vm]     += 1

    x          = np.arange(4)
    bar_width  = 0.35
    colors_avro = ['#d32f2f', '#388e3c', '#f57c00', '#1976d2']
    colors_rr   = ['#ef9a9a', '#a5d6a7', '#ffcc80', '#90caf9']

    bars_avro = ax.bar(x - bar_width/2,
                       [avro_counts[i] for i in range(4)],
                       bar_width,
                       label='AVRO',
                       color=colors_avro,
                       edgecolor='white',
                       linewidth=0.8)

    bars_rr = ax.bar(x + bar_width/2,
                     [rr_counts[i] for i in range(4)],
                     bar_width,
                     label='Round Robin',
                     color=colors_rr,
                     edgecolor='white',
                     linewidth=0.8)

    # Add count labels on bars
    for bar in bars_avro:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2, h + 1,
                str(int(h)), ha='center', va='bottom',
                fontsize=9, fontweight='bold')

    for bar in bars_rr:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2, h + 1,
                str(int(h)), ha='center', va='bottom',
                fontsize=9)

    ax.set_xlabel('Virtual Machine', fontsize=11)
    ax.set_ylabel('Number of Tasks Assigned', fontsize=11)
    ax.set_title('VM Selection Distribution: AVRO vs Round Robin', fontsize=13)
    ax.set_xticks(x)
    ax.set_xticklabels(VM_LABELS, fontsize=9)
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3, axis='y')

    # Annotate the overloaded VM
    ax.annotate('RR sends tasks\nto overloaded VM!',
                xy=(0 + bar_width/2, rr_counts[0]),
                xytext=(0.8, rr_counts[0] + 20),
                fontsize=8, color='red',
                arrowprops=dict(arrowstyle='->', color='red'))


def plot_fitness_comparison(ax, num_tasks=100):
    """
    Plot 3 — Cumulative average fitness over sequential tasks.
    Shows AVRO consistently outperforms RR over time.
    """
    avro = AVROScheduler(pop_size=10, max_iter=100)
    rr   = RoundRobinScheduler(num_vms=4)

    avro_cumulative = []
    rr_cumulative   = []

    avro_running_total = 0
    rr_running_total   = 0

    for t in range(1, num_tasks + 1):
        avro_vm = avro.select_vm(VM_STATS)
        rr_vm   = rr.select_vm(VM_STATS)

        avro_running_total += compute_fitness(VM_STATS[avro_vm])
        rr_running_total   += compute_fitness(VM_STATS[rr_vm])

        avro_cumulative.append(avro_running_total / t)
        rr_cumulative.append(rr_running_total / t)

    tasks = range(1, num_tasks + 1)

    ax.plot(tasks, avro_cumulative,
            color='steelblue', linewidth=2.5,
            label='AVRO')
    ax.plot(tasks, rr_cumulative,
            color='tomato', linewidth=2.5,
            linestyle='--', label='Round Robin')

    ax.fill_between(tasks, avro_cumulative, rr_cumulative,
                    alpha=0.1, color='green',
                    label='AVRO advantage')

    final_improvement = (
        (avro_cumulative[-1] - rr_cumulative[-1]) /
        rr_cumulative[-1] * 100
    )
    ax.text(0.98, 0.15,
            f'Final improvement:\n{final_improvement:.1f}%',
            transform=ax.transAxes,
            ha='right', fontsize=10,
            bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.5))

    ax.set_xlabel('Number of Tasks Scheduled', fontsize=11)
    ax.set_ylabel('Cumulative Average Fitness', fontsize=11)
    ax.set_title('Cumulative Average Fitness: AVRO vs Round Robin', fontsize=13)
    ax.legend(fontsize=10)
    ax.set_ylim(0, 1.0)
    ax.grid(True, alpha=0.3)


def plot_vm_fitness_scores(ax):
    """
    Plot 4 — Fitness score of each VM.
    Context for why AVRO makes the choices it does.
    """
    scores = [compute_fitness(vm) for vm in VM_STATS]
    colors = ['#d32f2f', '#388e3c', '#f57c00', '#1976d2']

    bars = ax.bar(VM_LABELS, scores,
                  color=colors,
                  edgecolor='white',
                  linewidth=0.8)

    for bar, score in zip(bars, scores):
        ax.text(bar.get_x() + bar.get_width()/2,
                bar.get_height() + 0.02,
                f'{score:.3f}',
                ha='center', va='bottom',
                fontsize=11, fontweight='bold')

    ax.set_ylabel('Fitness Score', fontsize=11)
    ax.set_title('VM Fitness Scores\n(Higher = Better Candidate)', fontsize=13)
    ax.set_ylim(0, 1.0)
    ax.grid(True, alpha=0.3, axis='y')
    ax.axhline(y=0.5, color='gray', linestyle='--',
               linewidth=1, label='Threshold (0.5)')
    ax.legend(fontsize=9)


def main():
    print("Generating plots...")

    fig = plt.figure(figsize=(16, 12))
    fig.suptitle(
        'AVRO Scheduler Performance Analysis\n'
        'SDN-Based Intelligent Load Balancing and Task Scheduling',
        fontsize=14, fontweight='bold', y=0.98
    )

    gs   = gridspec.GridSpec(2, 2, figure=fig,
                             hspace=0.4, wspace=0.35)
    ax1  = fig.add_subplot(gs[0, 0])
    ax2  = fig.add_subplot(gs[0, 1])
    ax3  = fig.add_subplot(gs[1, 0])
    ax4  = fig.add_subplot(gs[1, 1])

    plot_vm_fitness_scores(ax4)
    print("  Plot 4 done (VM fitness scores)")

    plot_convergence(ax1)
    print("  Plot 1 done (convergence)")

    plot_vm_selection_distribution(ax2)
    print("  Plot 2 done (VM selection distribution)")

    plot_fitness_comparison(ax3)
    print("  Plot 3 done (cumulative fitness)")

    output_path = os.path.join(
        os.path.dirname(__file__), 'avro_analysis.png')
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"\nSaved to: {output_path}")
    plt.show()


if __name__ == "__main__":
    main()