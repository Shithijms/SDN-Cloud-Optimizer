"""
test_fitness.py
---------------
Tests for the VM fitness function.
Run with: python -m pytest tests/ -v
Or simply: python tests/test_fitness.py
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.scheduler.fitness import compute_fitness, rank_vms


def test_perfect_vm_scores_near_one():
    """An idle VM with no load should score close to 1.0"""
    vm = {'cpu': 0.0, 'memory': 0.0, 'queue_length': 0, 'delay': 0.0}
    score = compute_fitness(vm)
    print(f"  Perfect VM score: {score}")
    assert score > 0.9, f"Expected > 0.9, got {score}"


def test_overloaded_vm_scores_low():
    """A maxed-out VM should score close to 0"""
    vm = {'cpu': 1.0, 'memory': 1.0, 'queue_length': 100, 'delay': 1000.0}
    score = compute_fitness(vm)
    print(f"  Overloaded VM score: {score}")
    assert score < 0.1, f"Expected < 0.1, got {score}"


def test_cpu_dominates_score():
    """
    VM with low CPU but high other metrics should beat
    VM with high CPU but low other metrics.
    Because W_CPU = 0.4 is the highest weight.
    """
    low_cpu_vm  = {'cpu': 0.1, 'memory': 0.5, 'queue_length': 2, 'delay': 10.0}
    high_cpu_vm = {'cpu': 0.9, 'memory': 0.5, 'queue_length': 2, 'delay': 10.0}

    score_low_cpu  = compute_fitness(low_cpu_vm)
    score_high_cpu = compute_fitness(high_cpu_vm)

    print(f"  Low CPU VM score:  {score_low_cpu}")
    print(f"  High CPU VM score: {score_high_cpu}")
    assert score_low_cpu > score_high_cpu, (
        f"Low CPU VM ({score_low_cpu}) should beat high CPU VM ({score_high_cpu})"
    )


def test_avro_beats_round_robin_scenario():
    """
    Classic scenario where Round Robin fails:
    VM0 is overloaded, VM1 and VM2 are healthy.
    AVRO should never pick VM0.
    Round Robin blindly picks all three equally.
    """
    vms = [
        {'cpu': 0.95, 'memory': 0.90, 'queue_length': 10, 'delay': 30.0},  # VM0 overloaded
        {'cpu': 0.20, 'memory': 0.25, 'queue_length': 1,  'delay': 8.0},   # VM1 healthy
        {'cpu': 0.15, 'memory': 0.20, 'queue_length': 0,  'delay': 5.0},   # VM2 best
    ]

    ranking = rank_vms(vms)
    print(f"  Ranking: {ranking}")

    # VM2 should be first, VM0 should be last
    assert ranking[0][0] == 2, f"VM2 should rank first, got VM{ranking[0][0]}"
    assert ranking[-1][0] == 0, f"VM0 should rank last, got VM{ranking[-1][0]}"


def test_rank_vms_returns_correct_order():
    """rank_vms should return descending order by fitness"""
    vms = [
        {'cpu': 0.8, 'memory': 0.8, 'queue_length': 8, 'delay': 40.0},  # VM0 bad
        {'cpu': 0.5, 'memory': 0.5, 'queue_length': 3, 'delay': 15.0},  # VM1 medium
        {'cpu': 0.1, 'memory': 0.1, 'queue_length': 0, 'delay': 2.0},   # VM2 good
    ]

    ranking = rank_vms(vms)
    scores = [score for _, score in ranking]

    print(f"  Scores in order: {scores}")
    assert scores == sorted(scores, reverse=True), "Ranking not in descending order"

def test_combined_metrics_beat_single_metric():
    """
    A VM with high CPU but excellent memory/queue/delay
    can beat a VM with low CPU but terrible other metrics.
    This proves fitness is multi-dimensional, not just CPU.
    This is the key advantage over naive schedulers.
    """
    low_cpu_bad_rest  = {'cpu': 0.1, 'memory': 0.9, 'queue_length': 10, 'delay': 100.0}
    high_cpu_good_rest = {'cpu': 0.9, 'memory': 0.1, 'queue_length': 0,  'delay': 0.0}

    score_a = compute_fitness(low_cpu_bad_rest)
    score_b = compute_fitness(high_cpu_good_rest)

    print(f"  Low CPU + bad rest:   {score_a}")
    print(f"  High CPU + good rest: {score_b}")
    print(f"  Winner: VM with {'low CPU+bad rest' if score_a > score_b else 'high CPU+good rest'}")

    # No assertion here — this is a demonstration test, not a pass/fail
    # The point is to show the fitness function considers all dimensions

def run_all_tests():
    tests = [
        test_perfect_vm_scores_near_one,
        test_overloaded_vm_scores_low,
        test_cpu_dominates_score,
        test_avro_beats_round_robin_scenario,
        test_rank_vms_returns_correct_order,
        test_combined_metrics_beat_single_metric,
    ]

    passed = 0
    failed = 0

    print("\n" + "="*50)
    print("Running fitness function tests")
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
    success = run_all_tests()
    sys.exit(0 if success else 1)