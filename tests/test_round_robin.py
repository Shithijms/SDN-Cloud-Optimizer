"""
test_round_robin.py
-------------------
Tests for Round Robin baseline scheduler.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))

from src.scheduler.round_robin import RoundRobinScheduler
from src.scheduler.avro        import AVROScheduler
from src.scheduler.fitness     import compute_fitness


VM_STATS = [
    {'cpu': 0.95, 'memory': 0.90, 'queue_length': 10, 'delay': 30.0},  # VM0 overloaded
    {'cpu': 0.30, 'memory': 0.40, 'queue_length': 1,  'delay': 8.0},   # VM1 healthy
    {'cpu': 0.60, 'memory': 0.55, 'queue_length': 3,  'delay': 15.0},  # VM2 moderate
    {'cpu': 0.20, 'memory': 0.30, 'queue_length': 0,  'delay': 5.0},   # VM3 best
]


def test_cycles_through_all_vms():
    """Round Robin must visit every VM in order"""
    rr  = RoundRobinScheduler(num_vms=4)
    seq = [rr.select_vm() for _ in range(8)]

    print(f"  Sequence over 8 tasks: {seq}")
    assert seq == [0, 1, 2, 3, 0, 1, 2, 3], (
        f"Expected [0,1,2,3,0,1,2,3], got {seq}"
    )


def test_ignores_vm_stats():
    """Round Robin should give same result regardless of VM stats passed"""
    rr = RoundRobinScheduler(num_vms=4)

    result_with_stats    = rr.select_vm(VM_STATS)
    rr.reset()
    result_without_stats = rr.select_vm()
    rr.reset()
    result_none          = rr.select_vm(None)

    print(f"  With stats: {result_with_stats}")
    print(f"  Without stats: {result_without_stats}")
    print(f"  None: {result_none}")

    assert result_with_stats == result_without_stats == result_none == 0


def test_equal_distribution():
    """Over many tasks, each VM should receive equal share"""
    rr         = RoundRobinScheduler(num_vms=4)
    num_tasks  = 1000

    for _ in range(num_tasks):
        rr.select_vm()

    dist = rr.get_distribution()
    print(f"  Distribution over {num_tasks} tasks: {dist}")

    for vm_id, count in dist.items():
        assert count == 250, (
            f"VM{vm_id} received {count} tasks, expected 250"
        )


def test_reset_works():
    """After reset, cycling should restart from VM0"""
    rr = RoundRobinScheduler(num_vms=4)

    rr.select_vm()
    rr.select_vm()
    rr.reset()

    first_after_reset = rr.select_vm()
    print(f"  First selection after reset: VM{first_after_reset}")
    assert first_after_reset == 0


def test_sends_tasks_to_overloaded_vm():
    """
    This test demonstrates Round Robin's core weakness.
    It sends tasks to VM0 (overloaded) just as often as VM3 (best).
    AVRO would never do this.
    """
    rr        = RoundRobinScheduler(num_vms=4)
    num_tasks = 400

    for _ in range(num_tasks):
        rr.select_vm(VM_STATS)

    dist = rr.get_distribution()
    print(f"  Distribution: {dist}")
    print(f"  VM0 (overloaded) received: {dist[0]} tasks ({dist[0]/num_tasks*100:.1f}%)")
    print(f"  VM3 (best)       received: {dist[3]} tasks ({dist[3]/num_tasks*100:.1f}%)")
    print(f"  Round Robin is BLIND to VM load — sends equal tasks to all")

    # This assert confirms the weakness — equal distribution despite unequal load
    assert dist[0] == dist[3], (
        "Round Robin should send equal tasks to both overloaded and healthy VMs"
    )


def test_avro_vs_round_robin_fitness():
    """
    Head-to-head comparison — the key result for your report.
    AVRO fitness should significantly exceed Round Robin.
    """
    avro      = AVROScheduler(pop_size=10, max_iter=100)
    rr        = RoundRobinScheduler(num_vms=4)
    num_tasks = 100

    avro_total_fitness = 0
    rr_total_fitness   = 0

    for _ in range(num_tasks):
        avro_vm = avro.select_vm(VM_STATS)
        rr_vm   = rr.select_vm(VM_STATS)

        avro_total_fitness += compute_fitness(VM_STATS[avro_vm])
        rr_total_fitness   += compute_fitness(VM_STATS[rr_vm])

    avro_avg = avro_total_fitness / num_tasks
    rr_avg   = rr_total_fitness   / num_tasks
    improvement = (avro_avg - rr_avg) / rr_avg * 100

    print(f"\n  {'Metric':<30} {'AVRO':>10} {'Round Robin':>12}")
    print(f"  {'-'*52}")
    print(f"  {'Avg Fitness Score':<30} {avro_avg:>10.4f} {rr_avg:>12.4f}")
    print(f"  {'Total Fitness':<30} {avro_total_fitness:>10.2f} {rr_total_fitness:>12.2f}")
    print(f"  {'Improvement':<30} {improvement:>10.1f}%")

    assert avro_avg > rr_avg, (
        f"AVRO ({avro_avg:.4f}) must outperform Round Robin ({rr_avg:.4f})"
    )
    assert improvement > 20, (
        f"Expected >20% improvement, got {improvement:.1f}%"
    )


def run_all_tests():
    tests = [
        test_cycles_through_all_vms,
        test_ignores_vm_stats,
        test_equal_distribution,
        test_reset_works,
        test_sends_tasks_to_overloaded_vm,
        test_avro_vs_round_robin_fitness,
    ]

    passed = 0
    failed = 0

    print("\n" + "="*50)
    print("Running Round Robin tests")
    print("="*50)

    for test in tests:
        try:
            print(f"\n{test.__name__}")
            test()
            print(f"  PASSED")
            passed += 1
        except AssertionError as e:
            print(f"  FAILED: {e}")
            failed += 1

    print("\n" + "="*50)
    print(f"Results: {passed} passed, {failed} failed")
    print("="*50)
    return failed == 0


if __name__ == "__main__":
    import sys
    success = run_all_tests()
    sys.exit(0 if success else 1)
    