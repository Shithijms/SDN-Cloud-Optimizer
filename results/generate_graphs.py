"""
generate_graphs.py
------------------
Generate a set of analysis plots for different test-derived conditions.
Run from project root: python results/generate_graphs.py

Creates PNG files in the `results/` folder for the following conditions:
 - default: 4-VM scenario used in tests and avro analysis
 - classic_3: the 3-VM scenario used in fitness tests (Round Robin failure)
 - many_vms: randomized 8-VM scenario to stress-test AVRO vs RR
 - monitor_csv: time-series plots read from monitor CSV if present

This script re-uses the scheduler API from `src/scheduler` (AVRO + Round Robin)
and the fitness function to produce comparable plots.
"""

import os
import sys
import csv
import json
import argparse
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Publication-style defaults
plt.rcParams.update({
    'font.size': 10,
    'font.family': 'serif',
    'axes.titlesize': 12,
    'axes.labelsize': 10,
    'legend.fontsize': 9,
    'figure.dpi': 150,
})

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.scheduler.avro import AVROScheduler
from src.scheduler.round_robin import RoundRobinScheduler
from src.scheduler.fitness import compute_fitness

# Output formats saved for paper inclusion
EXPORT_FORMATS = ('png', 'svg', 'pdf')

# Metadata collected for each generated figure (written to JSON/CSV)
FIGURES_META = {}


# -------------------- Scenarios (derived from tests) ---------------------
DEFAULT_VM_STATS = [
    {'cpu': 0.95, 'memory': 0.90, 'queue_length': 10, 'delay': 30.0},
    {'cpu': 0.30, 'memory': 0.40, 'queue_length': 1,  'delay': 8.0},
    {'cpu': 0.60, 'memory': 0.55, 'queue_length': 3,  'delay': 15.0},
    {'cpu': 0.20, 'memory': 0.30, 'queue_length': 0,  'delay': 5.0},
]

CLASSIC_3_VMS = [
    {'cpu': 0.95, 'memory': 0.90, 'queue_length': 10, 'delay': 30.0},
    {'cpu': 0.20, 'memory': 0.25, 'queue_length': 1,  'delay': 8.0},
    {'cpu': 0.15, 'memory': 0.20, 'queue_length': 0,  'delay': 5.0},
]


def ensure_results_dir():
    out_dir = os.path.join(os.path.dirname(__file__))
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def plot_vm_fitness_scores(vm_stats, labels=None, out_path=None, title=None):
    """Bar chart of fitness scores for a VM list."""
    scores = [compute_fitness(vm) for vm in vm_stats]
    if labels is None:
        labels = [f'VM{i}' for i in range(len(vm_stats))]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    bars = ax.bar(labels, scores, color='tab:blue', edgecolor='white')
    ax.set_ylim(0, 1.05)
    ax.set_ylabel('Fitness Score')
    ax.set_title(title or 'VM Fitness Scores')
    for bar, s in zip(bars, scores):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height()+0.02,
                f'{s:.3f}', ha='center', va='bottom', fontsize=9)

    if out_path:
        fig.tight_layout()
        base = os.path.splitext(out_path)[0]
        saved = save_figure_formats(fig, base)
        caption = (
            (title or 'VM Fitness Scores') +
            ' — Bar chart of per-VM fitness (higher is better).'
        )
        metrics = {'scores': scores}
        register_figure(os.path.basename(base), caption, metrics, saved)
        plt.close(fig)
    else:
        return fig


def compare_avro_vs_rr(vm_stats, num_tasks=300, name='default'):
    """Generate two-panel plot: distribution + cumulative average fitness."""
    avro = AVROScheduler()
    rr = RoundRobinScheduler(num_vms=len(vm_stats))

    avro_counts = {i: 0 for i in range(len(vm_stats))}
    rr_counts = {i: 0 for i in range(len(vm_stats))}

    avro_cum = []
    rr_cum = []
    avro_total = 0.0
    rr_total = 0.0

    for t in range(1, num_tasks + 1):
        avro_vm = avro.select_vm(vm_stats)
        rr_vm = rr.select_vm(vm_stats)

        avro_counts[avro_vm] += 1
        rr_counts[rr_vm] += 1

        avro_total += compute_fitness(vm_stats[avro_vm])
        rr_total += compute_fitness(vm_stats[rr_vm])

        avro_cum.append(avro_total / t)
        rr_cum.append(rr_total / t)

    out_dir = ensure_results_dir()
    base = os.path.join(out_dir, f'avro_vs_rr_{name}')

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    # Distribution bars
    x = np.arange(len(vm_stats))
    bw = 0.35
    ax1.bar(x - bw/2, [avro_counts[i] for i in x], bw, label='AVRO', color='tab:blue')
    ax1.bar(x + bw/2, [rr_counts[i] for i in x], bw, label='Round Robin', color='tab:orange')
    ax1.set_xticks(x)
    ax1.set_xticklabels([f'VM{i}' for i in x])
    ax1.set_xlabel('VM')
    ax1.set_ylabel('Tasks assigned')
    ax1.set_title('VM Selection Distribution')
    ax1.legend()

    # Cumulative average fitness
    tasks = range(1, num_tasks + 1)
    ax2.plot(tasks, avro_cum, label='AVRO', color='tab:blue')
    ax2.plot(tasks, rr_cum, label='Round Robin', color='tab:orange', linestyle='--')
    ax2.set_xlabel('Scheduled tasks')
    ax2.set_ylabel('Cumulative avg fitness')
    ax2.set_title('Cumulative Average Fitness')
    ax2.legend()

    fig.suptitle(f'AVRO vs Round Robin — {name}', fontsize=14)
    fig.tight_layout(rect=[0, 0.03, 1, 0.95])

    # Metrics for paper table
    final_avro = avro_cum[-1]
    final_rr = rr_cum[-1]
    improvement_pct = ((final_avro - final_rr) / final_rr * 100) if final_rr > 0 else None
    metrics = {
        'final_avro': final_avro,
        'final_rr': final_rr,
        'improvement_pct': improvement_pct,
        'avro_counts': avro_counts,
        'rr_counts': rr_counts,
        'num_tasks': num_tasks,
    }

    saved = save_figure_formats(fig, base)
    caption = (
        f'VM selection distribution and cumulative average fitness over {num_tasks} tasks '
        f'for AVRO vs Round Robin (scenario: {name}). AVRO final avg fitness={final_avro:.3f}, '
        f'RR final avg fitness={final_rr:.3f}, improvement={improvement_pct:.1f}%.'
    )
    register_figure(os.path.basename(base), caption, metrics, saved)
    plt.close(fig)


def avro_convergence(vm_stats, num_runs=8, name='default'):
    """Plot AVRO convergence curves over multiple runs."""
    scheduler = AVROScheduler()
    histories = []
    for _ in range(num_runs):
        _, history = scheduler.select_vm(vm_stats, track_convergence=True)
        histories.append(history)

    max_iter = scheduler.max_iter
    arr = np.array(histories)
    mean_hist = arr.mean(axis=0)
    std_hist = arr.std(axis=0)
    iters = range(1, max_iter + 1)

    out_dir = ensure_results_dir()
    base = os.path.join(out_dir, f'avro_convergence_{name}')

    fig, ax = plt.subplots(figsize=(8, 4.5))
    for h in histories:
        ax.plot(iters, h, alpha=0.12, color='steelblue')
    ax.plot(iters, mean_hist, color='steelblue', linewidth=2.2, label='Mean')
    ax.fill_between(iters, mean_hist - std_hist, mean_hist + std_hist, alpha=0.18, color='steelblue')
    ax.set_xlabel('Iteration')
    ax.set_ylabel('Best fitness')
    ax.set_title(f'AVRO Convergence — {name}')
    ax.set_ylim(0, 1.05)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    saved = save_figure_formats(fig, base)
    metrics = {
        'num_runs': num_runs,
        'mean_final': float(mean_hist[-1]),
        'std_final': float(std_hist[-1]),
    }
    caption = (
        f'AVRO convergence across {num_runs} independent runs (scenario: {name}). '
        f'Mean final fitness={metrics["mean_final"]:.3f} ± {metrics["std_final"]:.3f}.'
    )
    register_figure(os.path.basename(base), caption, metrics, saved)
    plt.close(fig)


def plot_monitor_csv(csv_path=None, name='monitor'):
    """Read monitor CSV and plot time-series per-VM for CPU and queue."""
    out_dir = ensure_results_dir()
    if csv_path is None:
        csv_path = os.path.join(out_dir, 'monitoring_log.csv')

    if not os.path.exists(csv_path):
        print(f"Monitor CSV not found at {csv_path}; skipping monitor plots.")
        return

    # Read CSV, group by vm_id
    times_by_vm = {}
    cpu_by_vm = {}
    queue_by_vm = {}

    with open(csv_path, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            vid = int(row.get('vm_id', row.get('vm', 0)))
            t = float(row.get('snapshot_time', row.get('timestamp', 0)))
            cpu = float(row['cpu'])
            q = int(float(row['queue_length']))

            times_by_vm.setdefault(vid, []).append(t)
            cpu_by_vm.setdefault(vid, []).append(cpu)
            queue_by_vm.setdefault(vid, []).append(q)

    # Convert times to relative seconds per VM
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    for vid in sorted(times_by_vm.keys()):
        t0 = times_by_vm[vid][0]
        rel_t = [x - t0 for x in times_by_vm[vid]]
        ax1.plot(rel_t, cpu_by_vm[vid], label=f'VM{vid}')
        ax2.plot(rel_t, queue_by_vm[vid], label=f'VM{vid}')

    ax1.set_ylabel('CPU usage')
    ax1.set_title('CPU Usage Over Time')
    ax1.legend(fontsize=8)
    ax1.grid(alpha=0.3)

    ax2.set_ylabel('Queue length')
    ax2.set_xlabel('Seconds since first snapshot')
    ax2.set_title('Queue Length Over Time')
    ax2.legend(fontsize=8)
    ax2.grid(alpha=0.3)

    base = os.path.join(out_dir, f'monitor_timeseries_{name}')
    fig.tight_layout()
    saved = save_figure_formats(fig, base)
    caption = f'Monitor time-series from {os.path.basename(csv_path)}: CPU and queue length per VM over time.'
    metrics = {'csv_path': csv_path, 'vm_count': len(times_by_vm)}
    register_figure(os.path.basename(base), caption, metrics, saved)
    plt.close(fig)


def many_vms_random(num_vms=8, name='many_vms'):
    rng = np.random.default_rng(seed=42)
    vm_stats = []
    for i in range(num_vms):
        vm_stats.append({
            'cpu': float(rng.random() * 0.9),
            'memory': float(0.1 + rng.random() * 0.8),
            'queue_length': int(rng.integers(0, 10)),
            'delay': float(1.0 + rng.random() * 50.0),
        })

    out_dir = ensure_results_dir()
    base = os.path.join(out_dir, f'fitness_{name}')
    fig = plot_vm_fitness_scores(vm_stats, labels=[f'VM{i}' for i in range(num_vms)],
                                 out_path=None,
                                 title=f'Random {num_vms}-VM Fitness')
    # If plot_vm_fitness_scores returned a figure, save it via helper
    if fig is not None:
        saved = save_figure_formats(fig, base)
        caption = f'Random {num_vms}-VM fitness distribution (publication-ready)'
        metrics = {'num_vms': num_vms}
        register_figure(os.path.basename(base), caption, metrics, saved)
        plt.close(fig)

    compare_avro_vs_rr(vm_stats, num_tasks=400, name=name)
    avro_convergence(vm_stats, num_runs=6, name=name)


def save_figure_formats(fig, base, formats=EXPORT_FORMATS, dpi=150):
    """Save a matplotlib Figure to multiple formats and return saved paths."""
    saved = []
    for fmt in formats:
        path = f"{base}.{fmt}"
        fig.savefig(path, dpi=dpi, bbox_inches='tight')
        saved.append(path)
        print(f"Saved: {path}")
    return saved


def register_figure(basename, caption, metrics, files):
    """Register a generated figure in the global metadata dictionary."""
    FIGURES_META[basename] = {
        'caption': caption,
        'metrics': metrics,
        'files': files,
    }


def write_metadata(out_dir):
    """Write JSON, CSV and markdown caption files for all registered figures."""
    json_path = os.path.join(out_dir, 'figures_metadata.json')
    csv_path = os.path.join(out_dir, 'figures_metrics.csv')
    md_path = os.path.join(out_dir, 'figure_captions.md')

    # JSON
    with open(json_path, 'w') as f:
        json.dump(FIGURES_META, f, indent=2)

    # CSV (one row per figure)
    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['figure', 'files', 'caption', 'metrics_json'])
        for k, v in FIGURES_META.items():
            writer.writerow([k, ';'.join(v['files']), v['caption'], json.dumps(v['metrics'])])

    # Markdown captions + LaTeX include snippets
    with open(md_path, 'w') as f:
        f.write('# Figure captions and LaTeX snippets\n\n')
        for k, v in FIGURES_META.items():
            f.write(f'## {k}\n')
            f.write(f"**Caption:** {v['caption']}\n\n")
            first_pdf = next((p for p in v['files'] if p.endswith('.pdf')), v['files'][0])
            f.write('LaTeX snippet:\n')
            f.write('''\n''')
            f.write('\\begin{figure}[ht]\n\\centering\n')
            f.write(f"\\includegraphics[width=0.8\\linewidth]{{{os.path.basename(first_pdf)}}}\n")
            f.write(f"\\caption{{{v['caption']}}}\n")
            f.write(f"\\label{{fig:{k}}}\n\\end{{figure}}\n\n")

    print(f'Wrote metadata: {json_path}, {csv_path}, {md_path}')


def main():
    out_dir = ensure_results_dir()

    # Default 4-VM scenario
    plot_vm_fitness_scores(DEFAULT_VM_STATS,
                           labels=['VM0', 'VM1', 'VM2', 'VM3'],
                           out_path=os.path.join(out_dir, 'fitness_default.png'),
                           title='Default 4-VM Fitness Scores')
    compare_avro_vs_rr(DEFAULT_VM_STATS, num_tasks=300, name='default')
    avro_convergence(DEFAULT_VM_STATS, num_runs=8, name='default')

    # Classic 3-VM scenario from fitness tests
    plot_vm_fitness_scores(CLASSIC_3_VMS,
                           labels=['VM0', 'VM1', 'VM2'],
                           out_path=os.path.join(out_dir, 'fitness_classic3.png'),
                           title='Classic 3-VM Fitness Scores')
    compare_avro_vs_rr(CLASSIC_3_VMS, num_tasks=250, name='classic3')
    avro_convergence(CLASSIC_3_VMS, num_runs=6, name='classic3')

    # Many-VM random scenario
    many_vms_random(8, name='8_vms')

    # Monitor CSV (if present)
    csv_candidates = [
        os.path.join(out_dir, 'demo_monitoring_log.csv'),
        os.path.join(out_dir, 'test_monitoring_log.csv'),
        os.path.join(out_dir, 'monitoring_log.csv'),
    ]
    csv_path = next((p for p in csv_candidates if os.path.exists(p)), None)
    plot_monitor_csv(csv_path, name='collected')

    # Write metadata for inclusion in reports/papers
    write_metadata(out_dir)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate graphs for different scenarios')
    parser.add_argument('--skip-monitor', action='store_true', help='Skip monitor CSV plots')
    args = parser.parse_args()

    if args.skip_monitor:
        # simple main that skips monitor CSV
        out_dir = ensure_results_dir()
        plot_vm_fitness_scores(DEFAULT_VM_STATS,
                               labels=['VM0', 'VM1', 'VM2', 'VM3'],
                               out_path=os.path.join(out_dir, 'fitness_default.png'),
                               title='Default 4-VM Fitness Scores')
        compare_avro_vs_rr(DEFAULT_VM_STATS, num_tasks=300, name='default')
        avro_convergence(DEFAULT_VM_STATS, num_runs=8, name='default')
        many_vms_random(8, name='8_vms')
        write_metadata(out_dir)
    else:
        main()
