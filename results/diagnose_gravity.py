"""
diagnose_gravity.py
-------------------
Diagnoses why AVRO underperforms in Gravity workload.
Run: python results/diagnose_gravity.py
"""

import sys
import os
import numpy as np

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))

from src.scheduler.avro        import AVROScheduler
from src.scheduler.round_robin import RoundRobinScheduler
from src.scheduler.fitness     import compute_fitness, rank_vms
from src.scheduler.environment import CloudEnvironment
from src.scheduler.simulation  import generate_gravity_workload


def diagnose():
    print("\n" + "="*65)
    print("  GRAVITY WORKLOAD DIAGNOSIS")
    print("="*65)

    # Step 1 — what does gravity workload actually look like?
    tasks = generate_gravity_workload(200, num_vms=4)

    print(f"\n  Task profile distribution in Gravity workload:")
    profiles = {}
    for t in tasks:
        p = t['profile']
        profiles[p] = profiles.get(p, 0) + 1
    for p, count in sorted(profiles.items()):
        print(f"    {p:<8}: {count} tasks ({count/200*100:.1f}%)")

    # Step 2 — simulate and capture every decision
    print(f"\n  Tracing first 20 scheduling decisions (AVRO):")
    print(f"  {'Task':>5} {'Profile':<8} {'VM Stats at decision time':>30} "
          f"{'AVRO picks':>12} {'Best VM':>10} {'Match':>6}")
    print("  " + "-"*75)

    env   = CloudEnvironment(num_vms=4, seed=42)
    avro  = AVROScheduler(pop_size=10, max_iter=30)
    tasks_sorted = sorted(tasks, key=lambda t: t['arrival_time'])

    wrong_decisions = 0
    total_checked   = 0

    for task in tasks_sorted[:20]:
        vm_stats = env.get_vm_stats_list()
        ranking  = rank_vms(vm_stats)
        best_vm  = ranking[0][0]

        avro_pick = avro.select_vm(vm_stats)
        match     = "✓" if avro_pick == best_vm else "✗"

        if avro_pick != best_vm:
            wrong_decisions += 1
        total_checked += 1

        cpu_str = "/".join(f"{v['cpu']:.2f}" for v in vm_stats)
        print(f"  {task['task_id']:>5} {task['profile']:<8} "
              f"cpu=[{cpu_str}] "
              f"AVRO=VM{avro_pick} best=VM{best_vm} {match}")

        env.vms[avro_pick].assign_task(task)
        env.tick()

    print(f"\n  Wrong decisions in first 20: {wrong_decisions}/20")

    # Step 3 — check what happens to fitness over time in gravity
    print(f"\n  Fitness score trajectory (every 10 tasks):")
    print(f"  {'Task#':>6} {'VM0 fit':>9} {'VM1 fit':>9} "
          f"{'VM2 fit':>9} {'VM3 fit':>9} {'All saturated':>14}")
    print("  " + "-"*60)

    env2  = CloudEnvironment(num_vms=4, seed=42)
    tasks2 = sorted(tasks, key=lambda t: t['arrival_time'])

    for idx, task in enumerate(tasks2):
        vm_stats = env2.get_vm_stats_list()

        if idx % 10 == 0:
            scores       = [compute_fitness(vm) for vm in vm_stats]
            all_saturated = all(vm['cpu'] > 0.80 for vm in vm_stats)
            sat_str       = "YES ←" if all_saturated else "no"
            print(f"  {idx:>6} "
                  f"{scores[0]:>9.4f} {scores[1]:>9.4f} "
                  f"{scores[2]:>9.4f} {scores[3]:>9.4f} "
                  f"{sat_str:>14}")

        # Use round robin to avoid AVRO influence on state
        vm_pick = idx % 4
        env2.vms[vm_pick].assign_task(task)
        env2.tick()

    # Step 4 — the key question
    # In gravity, heavy tasks all go to one "hot" source VM
    # Check if AVRO is misreading the source pattern
    print(f"\n  Heavy task distribution by source:")
    source_counts = {}
    heavy_tasks   = [t for t in tasks if t['profile'] == 'heavy']
    for t in heavy_tasks:
        src = t.get('source_vm', 'unknown')
        source_counts[src] = source_counts.get(src, 0) + 1

    for src, count in sorted(source_counts.items()):
        print(f"    Source VM{src}: {count} heavy tasks")

    print(f"\n  Total heavy tasks: {len(heavy_tasks)}/200 "
          f"({len(heavy_tasks)/2:.1f}%)")
    print(f"\n  Diagnosis complete.")
    print("="*65)


if __name__ == "__main__":
    diagnose()