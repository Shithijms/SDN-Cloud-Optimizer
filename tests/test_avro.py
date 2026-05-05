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

def test_exploration_returns_valid_indices():
    """All exploration outputs must be valid VM indices"""
    scheduler = AVROScheduler(pop_size=10)
    num_vms = 4
    pop     = scheduler.initialize_population(num_vms)
    fitness = scheduler.compute_population_fitness(pop, VM_STATS)
    leader  = scheduler.select_leader(pop, fitness)

    # Force large F to trigger exploration
    F = 1.5
    new_pop = scheduler._exploration(pop, leader, F, num_vms)

    print(f"  Original pop: {pop}")
    print(f"  After exploration: {new_pop}")

    assert new_pop.shape == pop.shape
    assert new_pop.min() >= 0
    assert new_pop.max() < num_vms


def test_development_returns_valid_indices():
    """All development outputs must be valid VM indices"""
    scheduler = AVROScheduler(pop_size=10)
    num_vms = 4
    pop     = scheduler.initialize_population(num_vms)
    fitness = scheduler.compute_population_fitness(pop, VM_STATS)
    leader  = scheduler.select_leader(pop, fitness)

    # Force small F to trigger development
    F = 0.3
    new_pop = scheduler._development(pop, leader, F, num_vms, fitness)

    print(f"  Original pop: {pop}")
    print(f"  After development: {new_pop}")

    assert new_pop.shape == pop.shape
    assert new_pop.min() >= 0
    assert new_pop.max() < num_vms


def test_levy_flight_nonzero():
    """Levy flight should return nonzero values"""
    scheduler = AVROScheduler()
    values = [scheduler._levy_flight() for _ in range(100)]
    nonzero = sum(1 for v in values if abs(v) > 1e-10)

    print(f"  Nonzero Levy values: {nonzero}/100")
    assert nonzero > 90


def test_exploration_moves_population():
    """Exploration should change at least some population members"""
    scheduler = AVROScheduler(pop_size=10)
    num_vms   = 4

    # Realistic starting population — not all same index
    # All pointing to worst VM (VM0), leader should push toward VM3
    pop     = np.array([0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    fitness = scheduler.compute_population_fitness(pop, VM_STATS)

    # Manually set leader to VM3 (best VM) to force movement
    leader = 3
    F      = 1.5

    new_pop = scheduler._exploration(pop, leader, F, num_vms)

    changed = np.sum(new_pop != pop)
    print(f"  Members changed: {changed}/10")
    print(f"  Before: {pop}")
    print(f"  After:  {new_pop}")
    print(f"  Leader was: VM{leader} (best VM)")

    assert changed > 0, (
        f"With leader=VM3 and population all at VM0, "
        f"exploration should produce movement"
    )

def test_exploration_diversity():
    """
    Exploration should produce diverse outputs over many runs.
    Running 20 times from same start should not always give same result.
    """
    scheduler = AVROScheduler(pop_size=10)
    num_vms   = 4
    pop       = np.array([0, 1, 2, 3, 0, 1, 2, 3, 0, 1])
    fitness   = scheduler.compute_population_fitness(pop, VM_STATS)
    leader    = scheduler.select_leader(pop, fitness)

    results = set()
    for _ in range(20):
        F       = 1.5
        new_pop = scheduler._exploration(pop, leader, F, num_vms)
        results.add(tuple(new_pop))

    print(f"  Unique population outcomes in 20 runs: {len(results)}")
    assert len(results) > 1, (
        f"Exploration should be stochastic — got same result every time"
    )

def test_select_vm_returns_valid_index():
    """select_vm must return a valid VM index"""
    scheduler = AVROScheduler()
    result    = scheduler.select_vm(VM_STATS)

    print(f"  Selected VM: {result}")
    assert isinstance(result, int), f"Expected int, got {type(result)}"
    assert 0 <= result < len(VM_STATS), (
        f"VM index {result} out of range [0, {len(VM_STATS)})"
    )


def test_select_vm_avoids_overloaded():
    """
    Over many runs, AVRO should rarely or never select VM0 (overloaded).
    VM0 has fitness 0.071 vs VM3 fitness 0.747.
    """
    scheduler  = AVROScheduler(pop_size=10, max_iter=100)
    selections = [scheduler.select_vm(VM_STATS) for _ in range(50)]

    counts = {i: selections.count(i) for i in range(len(VM_STATS))}
    print(f"  Selections over 50 runs: {counts}")

    vm0_pct = counts[0] / 50 * 100
    vm3_pct = counts[3] / 50 * 100
    print(f"  VM0 (overloaded) selected: {vm0_pct:.1f}%")
    print(f"  VM3 (best)       selected: {vm3_pct:.1f}%")

    assert counts[3] > counts[0], (
        f"VM3 (best) should be selected more than VM0 (overloaded). "
        f"VM3={counts[3]}, VM0={counts[0]}"
    )


def test_select_vm_single_vm():
    """With only one VM, must select index 0"""
    scheduler = AVROScheduler()
    single_vm = [{'cpu': 0.5, 'memory': 0.5, 'queue_length': 2, 'delay': 10.0}]
    result    = scheduler.select_vm(single_vm)

    print(f"  Single VM result: {result}")
    assert result == 0


def test_select_vm_empty_raises():
    """Empty VM list should raise ValueError"""
    scheduler = AVROScheduler()
    try:
        scheduler.select_vm([])
        assert False, "Should have raised ValueError"
    except ValueError as e:
        print(f"  Correctly raised ValueError: {e}")


def test_convergence_tracking_shape():
    """Convergence history should have max_iter entries"""
    scheduler = AVROScheduler(max_iter=100)
    result, history = scheduler.select_vm(VM_STATS, track_convergence=True)

    print(f"  Selected VM: {result}")
    print(f"  History length: {len(history)}")
    print(f"  First fitness: {history[0]:.4f}")
    print(f"  Final fitness: {history[-1]:.4f}")

    assert len(history) == 100, (
        f"Expected 100 history entries, got {len(history)}"
    )


def test_convergence_is_nondecreasing():
    """
    Best fitness tracked over iterations should never decrease.
    We track the BEST seen so far, so it can only stay same or improve.
    """
    scheduler = AVROScheduler(max_iter=100)
    _, history = scheduler.select_vm(VM_STATS, track_convergence=True)

    violations = [
        i for i in range(1, len(history))
        if history[i] < history[i-1] - 1e-9
    ]

    print(f"  Convergence violations (decreases): {len(violations)}")
    print(f"  Start: {history[0]:.4f} → End: {history[-1]:.4f}")

    assert len(violations) == 0, (
        f"Convergence history decreased at iterations: {violations}"
    )


def test_avro_beats_random_selection():
    """
    AVRO average fitness should beat random VM selection
    over many independent runs.
    """
    from src.scheduler.fitness import compute_fitness

    scheduler    = AVROScheduler(pop_size=10, max_iter=100)
    num_runs     = 30

    avro_fitness   = []
    random_fitness = []

    for _ in range(num_runs):
        avro_vm   = scheduler.select_vm(VM_STATS)
        random_vm = np.random.randint(0, len(VM_STATS))

        avro_fitness.append(compute_fitness(VM_STATS[avro_vm]))
        random_fitness.append(compute_fitness(VM_STATS[random_vm]))

    avg_avro   = sum(avro_fitness)   / num_runs
    avg_random = sum(random_fitness) / num_runs

    print(f"  AVRO avg fitness:   {avg_avro:.4f}")
    print(f"  Random avg fitness: {avg_random:.4f}")
    print(f"  Improvement: {((avg_avro - avg_random) / avg_random * 100):.1f}%")

    assert avg_avro > avg_random, (
        f"AVRO ({avg_avro:.4f}) should beat random ({avg_random:.4f})"
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
        test_exploration_returns_valid_indices,
        test_development_returns_valid_indices,
        test_levy_flight_nonzero,
        test_exploration_moves_population,
        test_exploration_diversity,
        test_select_vm_returns_valid_index,
        test_select_vm_avoids_overloaded,
        test_select_vm_single_vm,
        test_select_vm_empty_raises,
        test_convergence_tracking_shape,
        test_convergence_is_nondecreasing,
        test_avro_beats_random_selection,
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

