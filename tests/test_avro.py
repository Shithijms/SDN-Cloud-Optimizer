"""
test_avro.py
------------
Tests for AVRO scheduler — built incrementally.
Stage 1: Population, Leader Selection, Satiety.
"""

import sys
import os
import numpy as np
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.scheduler.avro import AVROScheduler


# ── Shared test data ────────────────────────────────────────────
VM_STATS = [
    {'cpu': 0.95, 'memory': 0.90, 'queue_length': 10, 'delay': 30.0},  # VM0 overloaded
    {'cpu': 0.30, 'memory': 0.40, 'queue_length': 1,  'delay': 8.0},   # VM1 healthy
    {'cpu': 0.60, 'memory': 0.55, 'queue_length': 3,  'delay': 15.0},  # VM2 moderate
    {'cpu': 0.20, 'memory': 0.30, 'queue_length': 0,  'delay': 5.0},   # VM3 best
]


def test_population_shape():
    """Population should have exactly pop_size members"""
    scheduler = AVROScheduler(pop_size=10)
    pop = scheduler.initialize_population(num_vms=4)

    print(f"  Population: {pop}")
    print(f"  Shape: {pop.shape}")

    assert pop.shape == (10,), f"Expected shape (10,), got {pop.shape}"


def test_population_valid_vm_indices():
    """Every population member must be a valid VM index"""
    scheduler = AVROScheduler(pop_size=20)
    num_vms = 4
    pop = scheduler.initialize_population(num_vms=num_vms)

    print(f"  Population: {pop}")
    print(f"  Min: {pop.min()}, Max: {pop.max()}")

    assert pop.min() >= 0,        f"Found negative VM index: {pop.min()}"
    assert pop.max() < num_vms,   f"Found VM index >= num_vms: {pop.max()}"


def test_population_fitness_shape():
    """Fitness array should match population size"""
    scheduler = AVROScheduler(pop_size=10)
    pop = scheduler.initialize_population(num_vms=4)
    fitness = scheduler.compute_population_fitness(pop, VM_STATS)

    print(f"  Fitness scores: {fitness}")

    assert fitness.shape == (10,), f"Expected shape (10,), got {fitness.shape}"


def test_population_fitness_range():
    """All fitness scores must be in [0, 1]"""
    scheduler = AVROScheduler(pop_size=10)
    pop = scheduler.initialize_population(num_vms=4)
    fitness = scheduler.compute_population_fitness(pop, VM_STATS)

    print(f"  Min fitness: {fitness.min():.4f}")
    print(f"  Max fitness: {fitness.max():.4f}")

    assert fitness.min() > 0,  f"Fitness should be > 0, got {fitness.min()}"
    assert fitness.max() <= 1, f"Fitness should be <= 1, got {fitness.max()}"


def test_leader_is_valid_vm_index():
    """Leader must be a valid VM index"""
    scheduler = AVROScheduler(pop_size=10)
    pop = scheduler.initialize_population(num_vms=4)
    fitness = scheduler.compute_population_fitness(pop, VM_STATS)
    leader = scheduler.select_leader(pop, fitness)

    print(f"  Population: {pop}")
    print(f"  Fitness:    {fitness.round(4)}")
    print(f"  Leader VM:  {leader}")

    assert 0 <= leader < 4, f"Leader VM index {leader} out of range [0, 4)"


def test_leader_tends_toward_best_vm():
    """
    Over many selections, leader should favor high-fitness VMs.
    VM3 has highest fitness — should appear most as leader.
    """
    scheduler = AVROScheduler(pop_size=10)
    leader_counts = {0: 0, 1: 0, 2: 0, 3: 0}

    for _ in range(500):
        pop = scheduler.initialize_population(num_vms=4)
        fitness = scheduler.compute_population_fitness(pop, VM_STATS)
        leader = scheduler.select_leader(pop, fitness)
        if leader in leader_counts:
            leader_counts[leader] += 1

    print(f"  Leader selection counts over 500 runs: {leader_counts}")

    # VM3 (best) and VM1 (second best) should dominate
    best_vm_count = leader_counts[3] + leader_counts[1]
    worst_vm_count = leader_counts[0]

    assert best_vm_count > worst_vm_count * 2, (
        f"Good VMs selected {best_vm_count} times, "
        f"overloaded VM0 selected {worst_vm_count} times. "
        f"Expected good VMs to dominate significantly."
    )


def test_satiety_range_before_optimization():
    """F values before t_train should vary widely"""
    scheduler = AVROScheduler(max_iter=100, t_train=70)
    f_values = [scheduler.compute_satiety(i) for i in range(70)]

    f_min = min(f_values)
    f_max = max(f_values)

    print(f"  F range before optimization: [{f_min:.4f}, {f_max:.4f}]")
    assert f_max - f_min > 0.5, (
        f"F should vary widely before optimization stage, "
        f"range was only {f_max - f_min:.4f}"
    )


def test_satiety_clipped_after_optimization():
    """F values at/after t_train must be within [-delta2, delta2]"""
    scheduler = AVROScheduler(max_iter=100, t_train=70)
    delta2 = 0.0001

    f_values = [scheduler.compute_satiety(i) for i in range(70, 100)]

    print(f"  F values in optimization stage: {[round(f,6) for f in f_values[:5]]}...")
    for i, f in enumerate(f_values):
        assert abs(f) <= delta2 + 1e-10, (
            f"F={f} at iteration {70+i} exceeds delta2={delta2}"
        )


def test_exploration_triggered_when_f_large():
    """When |F| >= 1, algorithm should be in exploration mode"""
    scheduler = AVROScheduler(max_iter=100, t_train=70)

    # Early iterations tend to have large F
    early_f_values = [scheduler.compute_satiety(0) for _ in range(100)]
    large_f_count = sum(1 for f in early_f_values if abs(f) >= 1)

    print(f"  Large |F| (>=1) count at iteration 0: {large_f_count}/100")
    assert large_f_count > 20, (
        f"Expected some exploration-triggering F values early on, "
        f"only got {large_f_count}/100"
    )


def run_all_tests():
    tests = [
        test_population_shape,
        test_population_valid_vm_indices,
        test_population_fitness_shape,
        test_population_fitness_range,
        test_leader_is_valid_vm_index,
        test_leader_tends_toward_best_vm,
        test_satiety_range_before_optimization,
        test_satiety_clipped_after_optimization,
        test_exploration_triggered_when_f_large,
    ]

    passed = 0
    failed = 0

    print("\n" + "="*50)
    print("Running AVRO Stage 1 tests")
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

