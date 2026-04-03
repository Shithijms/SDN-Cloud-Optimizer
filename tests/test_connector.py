"""
test_connector.py
-----------------
Tests for VMConnector in both simulation and live modes.
Run: python tests/test_connector.py
"""

import sys
import os
import time

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))

from src.scheduler.connector  import (VMConnector, ConnectorMode,
                                       MockMonitorServer)
from src.scheduler.vm_state   import VMState
from src.scheduler.avro       import AVROScheduler


# ── Shared test VMs ──────────────────────────────────────────────
def make_test_vms():
    return [
        VMState(vm_id=0, cpu_cores=2, memory_gb=4.0,  base_delay=8.0),
        VMState(vm_id=1, cpu_cores=4, memory_gb=8.0,  base_delay=5.0),
        VMState(vm_id=2, cpu_cores=4, memory_gb=8.0,  base_delay=5.0),
        VMState(vm_id=3, cpu_cores=8, memory_gb=16.0, base_delay=3.0),
    ]


def test_simulation_mode_returns_stats():
    """Simulation mode should return stats for all VMs"""
    vms       = make_test_vms()
    connector = VMConnector(
        mode=ConnectorMode.SIMULATION, vm_list=vms)

    stats = connector.get_stats()

    print(f"  Got {len(stats)} VM stats")
    print(f"  Sample: {stats[0]}")

    assert len(stats) == 4
    assert all('cpu' in s for s in stats)
    assert all('memory' in s for s in stats)
    assert all('queue_length' in s for s in stats)
    assert all('delay' in s for s in stats)


def test_simulation_stats_valid_ranges():
    """All stats must be in valid ranges"""
    vms       = make_test_vms()
    connector = VMConnector(
        mode=ConnectorMode.SIMULATION, vm_list=vms)

    stats = connector.get_stats()

    for s in stats:
        assert 0.0 <= s['cpu']    <= 1.0, f"CPU out of range: {s['cpu']}"
        assert 0.0 <= s['memory'] <= 1.0, f"Memory out of range: {s['memory']}"
        assert s['queue_length']  >= 0,   f"Negative queue: {s['queue_length']}"
        assert s['delay']         >= 0,   f"Negative delay: {s['delay']}"

    print(f"  All {len(stats)} VMs have valid ranges")


def test_connector_feeds_avro():
    """Connector output must work directly as AVRO input"""
    vms       = make_test_vms()
    connector = VMConnector(
        mode=ConnectorMode.SIMULATION, vm_list=vms)
    scheduler = AVROScheduler(pop_size=10, max_iter=30)

    stats     = connector.get_stats()
    result    = scheduler.select_vm(stats)

    print(f"  AVRO selected VM{result} from connector stats")
    assert 0 <= result < 4


def test_live_mode_with_mock_server():
    """
    Live mode should fetch from HTTP endpoint.
    Uses MockMonitorServer to simulate Member 2's API.
    """
    vms    = make_test_vms()
    mock   = MockMonitorServer(vm_list=vms, port=6001)
    mock.start()

    # Point connector to mock server
    import src.scheduler.connector as conn_module
    original_url = conn_module.MONITOR_URL
    conn_module.MONITOR_URL = "http://localhost:6001/api/vm_stats"

    try:
        connector = VMConnector(mode=ConnectorMode.LIVE)
        stats     = connector.get_stats()

        print(f"  Live mode fetched {len(stats)} VM stats from mock")
        assert len(stats) == 4
        assert all('cpu' in s for s in stats)

    finally:
        conn_module.MONITOR_URL = original_url


def test_live_mode_fallback_on_failure():
    """
    If Member 2's API goes down, connector should use cached stats.
    """
    vms       = make_test_vms()
    mock      = MockMonitorServer(vm_list=vms, port=6002)
    mock.start()

    import src.scheduler.connector as conn_module
    original_url = conn_module.MONITOR_URL
    conn_module.MONITOR_URL = "http://localhost:6002/api/vm_stats"

    try:
        connector = VMConnector(mode=ConnectorMode.LIVE)

        # First fetch — populates cache
        stats1 = connector.get_stats()
        assert len(stats1) == 4
        print(f"  First fetch succeeded: {len(stats1)} VMs")

        # Point to dead URL — should use cache
        conn_module.MONITOR_URL = "http://localhost:9999/api/vm_stats"
        connector2 = VMConnector(mode=ConnectorMode.LIVE)
        connector2._last_stats = stats1
        connector2._last_fetch = time.time()

        stats2 = connector2.get_stats()
        print(f"  Fallback fetch succeeded: {len(stats2)} VMs from cache")
        assert len(stats2) == 4

    finally:
        conn_module.MONITOR_URL = original_url


def test_validation_clamps_out_of_range():
    """Connector should fix out-of-range values from Member 2"""
    vms       = make_test_vms()
    connector = VMConnector(
        mode=ConnectorMode.SIMULATION, vm_list=vms)

    # Simulate bad data from Member 2
    bad_stats = [
        {'vm_id': 0, 'cpu': 1.5,   'memory': -0.1,
         'queue_length': -2, 'delay': 5.0},
        {'vm_id': 1, 'cpu': 0.5,   'memory': 0.4,
         'queue_length': 2,  'delay': 8.0},
    ]

    validated = connector._validate_stats(bad_stats)

    print(f"  Before: cpu=1.5 → After: cpu={validated[0]['cpu']}")
    print(f"  Before: memory=-0.1 → After: memory={validated[0]['memory']}")
    print(f"  Before: queue=-2 → After: queue={validated[0]['queue_length']}")

    assert validated[0]['cpu']          == 1.0
    assert validated[0]['memory']       == 0.0
    assert validated[0]['queue_length'] == 0


def test_validation_catches_missing_fields():
    """Connector should raise clear error if Member 2 forgets a field"""
    vms       = make_test_vms()
    connector = VMConnector(
        mode=ConnectorMode.SIMULATION, vm_list=vms)

    # Missing 'delay' field — common mistake
    incomplete_stats = [
        {'vm_id': 0, 'cpu': 0.5, 'memory': 0.4, 'queue_length': 2}
    ]

    try:
        connector._validate_stats(incomplete_stats)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        print(f"  Correctly caught missing field: {e}")


def test_connection_test_simulation():
    """test_connection should report ok in simulation mode"""
    vms       = make_test_vms()
    connector = VMConnector(
        mode=ConnectorMode.SIMULATION, vm_list=vms)

    result = connector.test_connection()
    print(f"  Connection test result: {result}")

    assert result['status']  == 'ok'
    assert result['num_vms'] == 4


def run_all_tests():
    tests = [
        test_simulation_mode_returns_stats,
        test_simulation_stats_valid_ranges,
        test_connector_feeds_avro,
        test_live_mode_with_mock_server,
        test_live_mode_fallback_on_failure,
        test_validation_clamps_out_of_range,
        test_validation_catches_missing_fields,
        test_connection_test_simulation,
    ]

    passed = 0
    failed = 0

    print("\n" + "="*50)
    print("Running connector tests")
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
        except Exception as e:
            print(f"  ERROR: {e}")
            failed += 1

    print("\n" + "="*50)
    print(f"Results: {passed} passed, {failed} failed")
    print("="*50)
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)