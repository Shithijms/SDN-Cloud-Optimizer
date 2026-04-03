"""
test_integration.py
-------------------
Tests full pipeline: Member 2 → You → Member 1 direction.
Run AFTER Member 2's monitor_server.py is running.

python tests/test_integration.py
"""

import sys
import os
import json
import urllib.request

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))

from src.scheduler.connector import VMConnector, ConnectorMode
from src.scheduler.avro      import AVROScheduler


MONITOR_URL   = "http://localhost:6000/api/vm_stats"
SCHEDULER_URL = "http://localhost:5000/api/schedule"


def test_member2_api_reachable():
    """Member 2's monitor server must be running"""
    try:
        response = urllib.request.urlopen(MONITOR_URL, timeout=2)
        data     = json.loads(response.read())
        print(f"  Member 2 API: OK — {len(data)} VMs")
        assert len(data) == 4
    except Exception as e:
        print(f"  Member 2 API: UNREACHABLE — {e}")
        print(f"  Tell Member 2 to run: python monitor_server.py")
        assert False


def test_scheduler_api_reachable():
    """Your scheduler API must be running"""
    try:
        response = urllib.request.urlopen(
            "http://localhost:5000/api/status", timeout=2)
        data     = json.loads(response.read())
        print(f"  Scheduler API: OK — {data['scheduler']}")
    except Exception as e:
        print(f"  Scheduler API: UNREACHABLE — {e}")
        print(f"  Run: python src/scheduler/api.py")
        assert False


def test_full_pipeline():
    """
    Full pipeline test:
    1. Fetch stats from Member 2
    2. Send to your scheduler
    3. Get decision back
    """
    # Step 1 — get stats from Member 2
    response  = urllib.request.urlopen(MONITOR_URL, timeout=2)
    vm_stats  = json.loads(response.read())
    print(f"  Got {len(vm_stats)} VM stats from Member 2")

    # Step 2 — send to your scheduler
    body     = json.dumps(vm_stats).encode()
    req      = urllib.request.Request(
        SCHEDULER_URL,
        data=body,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    response  = urllib.request.urlopen(req, timeout=5)
    decision  = json.loads(response.read())

    print(f"  Scheduler decision: VM{decision['selected_vm_id']} "
          f"(fitness={decision['fitness_score']}, "
          f"time={decision['decision_ms']}ms)")

    assert 'selected_vm_id' in decision
    assert 0 <= decision['selected_vm_id'] < 4
    assert decision['fitness_score'] > 0


def test_queue_feedback():
    """
    After scheduling, Member 2's queue should update.
    """
    # Get initial queue lengths
    response1 = urllib.request.urlopen(MONITOR_URL, timeout=2)
    before    = json.loads(response1.read())
    before_q  = [vm['queue_length'] for vm in before]

    # Schedule a task
    body     = json.dumps(before).encode()
    req      = urllib.request.Request(
        SCHEDULER_URL,
        data=body,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    response  = urllib.request.urlopen(req, timeout=5)
    decision  = json.loads(response.read())
    chosen_vm = decision['selected_vm_id']

    # Get updated queue lengths
    response2 = urllib.request.urlopen(MONITOR_URL, timeout=2)
    after     = json.loads(response2.read())
    after_q   = [vm['queue_length'] for vm in after]

    print(f"  Before queues: {before_q}")
    print(f"  After queues:  {after_q}")
    print(f"  VM{chosen_vm} queue: {before_q[chosen_vm]} → {after_q[chosen_vm]}")

    assert after_q[chosen_vm] == before_q[chosen_vm] + 1, \
        f"VM{chosen_vm} queue should have increased by 1"


def run_all_tests():
    tests = [
        test_member2_api_reachable,
        test_scheduler_api_reachable,
        test_full_pipeline,
        test_queue_feedback,
    ]

    passed = 0
    failed = 0

    print("\n" + "="*55)
    print("Integration Tests — Member 2 ↔ Member 3 pipeline")
    print("="*55)
    print("Prerequisites:")
    print("  Terminal 1: python monitor_server.py  (Member 2)")
    print("  Terminal 2: python src/scheduler/api.py (you)")
    print("="*55)

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

    print("\n" + "="*55)
    print(f"Results: {passed} passed, {failed} failed")
    print("="*55)


if __name__ == "__main__":
    run_all_tests()