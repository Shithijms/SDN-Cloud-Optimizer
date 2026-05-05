"""
Member 2 - Test Script
Run this to verify ResourceMonitor works BEFORE integrating with Mininet.
Uses simulated mode — no Mininet needed.

Usage:
    python3 test_monitor.py
"""

import time
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from resource_monitor import ResourceMonitor

def test_basic_stats():
    print("=" * 50)
    print("TEST 1: Basic stats collection (simulated)")
    print("=" * 50)
    monitor = ResourceMonitor(simulated=True)
    stats = monitor.get_all_vm_stats()
    monitor.print_stats_table(stats)
    assert len(stats) == 4, "Should have 4 VMs"
    for vm in stats:
        assert 0.0 <= vm['cpu'] <= 1.0,    "CPU must be 0–1"
        assert 0.0 <= vm['memory'] <= 1.0, "Memory must be 0–1"
        assert vm['queue_length'] >= 0,    "Queue must be >= 0"
        assert vm['delay'] > 0,            "Delay must be > 0"
    print("\n✓ Test 1 PASSED\n")

def test_queue_tracking():
    print("=" * 50)
    print("TEST 2: Queue tracking")
    print("=" * 50)
    monitor = ResourceMonitor(simulated=True)

    # Assign 3 tasks to VM 0
    monitor.task_assigned(0)
    monitor.task_assigned(0)
    monitor.task_assigned(0)

    # Assign 1 task to VM 2
    monitor.task_assigned(2)

    stats = monitor.get_all_vm_stats()
    monitor.print_stats_table(stats)

    assert stats[0]['queue_length'] == 3, f"VM0 queue should be 3, got {stats[0]['queue_length']}"
    assert stats[1]['queue_length'] == 0, f"VM1 queue should be 0"
    assert stats[2]['queue_length'] == 1, f"VM2 queue should be 1"

    # Complete one task on VM 0
    monitor.task_completed(0)
    stats2 = monitor.get_all_vm_stats()
    assert stats2[0]['queue_length'] == 2, f"VM0 queue should be 2 after completion"

    print("✓ Test 2 PASSED\n")

def test_background_polling():
    print("=" * 50)
    print("TEST 3: Background polling thread")
    print("=" * 50)
    monitor = ResourceMonitor(simulated=True)
    monitor.start_background_polling(interval=1)

    print("Waiting 3 seconds for background polls...")
    time.sleep(3)

    latest = monitor.get_latest_stats()
    assert len(latest) > 0, "Should have latest stats from background thread"
    print(f"Latest stats have {len(latest)} VMs")
    monitor.print_stats_table(latest)

    monitor.stop_background_polling()
    print("✓ Test 3 PASSED\n")

def test_csv_export():
    print("=" * 50)
    print("TEST 4: CSV export")
    print("=" * 50)
    monitor = ResourceMonitor(simulated=True)

    # Generate some history
    for _ in range(5):
        monitor.get_all_vm_stats()
        time.sleep(0.1)

    monitor.save_to_csv('results/test_monitoring_log.csv')
    assert os.path.exists('results/test_monitoring_log.csv'), "CSV file not created"

    import csv
    with open('results/test_monitoring_log.csv') as f:
        rows = list(csv.DictReader(f))
    print(f"CSV contains {len(rows)} rows")
    print(f"Columns: {list(rows[0].keys())}")
    assert len(rows) == 5 * 4, f"Should have 20 rows (5 snapshots × 4 VMs), got {len(rows)}"
    print("✓ Test 4 PASSED\n")

def test_live_monitoring_demo():
    print("=" * 50)
    print("DEMO: Live monitoring for 10 seconds")
    print("(Simulates what happens during a real Mininet run)")
    print("=" * 50)
    monitor = ResourceMonitor(simulated=True)

    # Simulate tasks arriving and completing
    monitor.task_assigned(0)
    monitor.task_assigned(0)
    monitor.task_assigned(1)

    for i in range(5):
        stats = monitor.get_all_vm_stats()
        print(f"\n--- Poll {i+1} ---")
        monitor.print_stats_table(stats)

        # Simulate a task completing mid-run
        if i == 2:
            print("  [Event] Task completed on VM0")
            monitor.task_completed(0)
        if i == 3:
            print("  [Event] New task assigned to VM3")
            monitor.task_assigned(3)

        time.sleep(1)

    monitor.save_to_csv('results/demo_monitoring_log.csv')
    print("\n✓ Demo complete. CSV saved to results/demo_monitoring_log.csv")

if __name__ == '__main__':
    os.makedirs('results', exist_ok=True)

    test_basic_stats()
    test_queue_tracking()
    test_background_polling()
    test_csv_export()
    test_live_monitoring_demo()

    print("\n" + "=" * 50)
    print("ALL TESTS PASSED ✓")
    print("Your monitoring module is ready to integrate.")
    print("=" * 50)
