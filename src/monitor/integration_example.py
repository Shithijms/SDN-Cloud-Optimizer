"""
Member 2 - Integration Example
Shows exactly how your module connects to Member 1 (Ryu) and Member 3 (AVRO).
Share this file with your teammates so they know how to use your module.

TWO WAYS TO USE:
  1. With real Mininet (final project run)
  2. Simulated (for testing and demo)
"""

# ════════════════════════════════════════════════════════════
# HOW MEMBER 1 (RYU CONTROLLER) PLUGS IN YOUR OPENFLOW MONITOR
# ════════════════════════════════════════════════════════════
RYU_INTEGRATION_CODE = '''
# Add these lines to Member 1's ryu_app.py

from openflow_stats import OpenFlowMonitor
from resource_monitor import ResourceMonitor

# Create shared monitor instances
of_monitor = OpenFlowMonitor()
# resource_monitor is created after net.start() with real hosts

class LoadBalancerApp(app_manager.RyuApp):
    
    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def port_stats_reply_handler(self, ev):
        """Ryu calls this when switch sends port stats back."""
        for stat in ev.msg.body:
            of_monitor.update_port_stats(
                ev.msg.datapath.id,
                stat.port_no,
                stat.rx_bytes,
                stat.tx_bytes
            )
    
    def request_port_stats(self, datapath):
        """Call this every 2 seconds to trigger stats collection."""
        parser = datapath.ofproto_parser
        req = parser.OFPPortStatsRequest(datapath, 0, ofproto.OFPP_ANY)
        datapath.send_msg(req)
'''


# ════════════════════════════════════════════════════════════
# HOW MEMBER 3 (AVRO SCHEDULER) USES YOUR RESOURCE MONITOR
# ════════════════════════════════════════════════════════════
AVRO_INTEGRATION_CODE = '''
# Add these lines to Member 3's avro_scheduler.py

from resource_monitor import ResourceMonitor

# Member 3 receives the monitor object from the main runner
class AVROScheduler:
    def __init__(self, monitor):
        self.monitor = monitor   # <-- your ResourceMonitor
    
    def select_vm(self):
        """Main scheduling call — gets stats from your monitor."""
        vm_stats = self.monitor.get_all_vm_stats()   # YOUR METHOD
        best_vm  = self._optimize(vm_stats)
        return best_vm
    
    def _optimize(self, vm_stats):
        # AVRO fitness function uses vm_stats fields:
        # vm['cpu'], vm['memory'], vm['queue_length'], vm['delay']
        best = max(vm_stats, key=lambda vm: self._fitness(vm))
        return best['vm_id']
    
    def _fitness(self, vm):
        return (0.4 * (1 - vm['cpu']) +
                0.3 * (1 - vm['memory']) +
                0.2 * (1 / (vm['queue_length'] + 1)) +
                0.1 * (1 / (vm['delay'] + 1)))
'''


# ════════════════════════════════════════════════════════════
# FULL INTEGRATION DEMO (simulated — no Mininet needed)
# ════════════════════════════════════════════════════════════
if __name__ == '__main__':
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from resource_monitor import ResourceMonitor

    print("=" * 55)
    print("INTEGRATION DEMO — Member 2 ↔ Member 3 handshake")
    print("=" * 55)

    # --- Step 1: Member 2 starts the monitor ---
    monitor = ResourceMonitor(simulated=True)
    monitor.start_background_polling(interval=1)
    print("[Member2] Monitor started\n")

    # --- Step 2: Simulate AVRO scheduler (Member 3) asking for stats ---
    import time
    for task_num in range(1, 8):
        print(f"[Task {task_num}] Arrived — fetching VM stats...")
        vm_stats = monitor.get_all_vm_stats()

        # Simple fitness (this is what Member 3 does inside AVRO)
        def fitness(vm):
            return (0.4*(1-vm['cpu']) + 0.3*(1-vm['memory']) +
                    0.2*(1/(vm['queue_length']+1)) + 0.1*(1/(vm['delay']+1)))

        best = max(vm_stats, key=fitness)
        print(f"[AVRO]   → Selected VM{best['vm_id']} "
              f"(cpu={best['cpu']:.2f}, mem={best['memory']:.2f}, "
              f"queue={best['queue_length']}, delay={best['delay']:.1f}ms)")

        # Member 2 tracks the assignment
        monitor.task_assigned(best['vm_id'])

        # Simulate task finishing after a while
        if task_num > 3:
            monitor.task_completed(task_num % 4)
            print(f"[Event]  Task completed on VM{task_num % 4}")

        time.sleep(0.5)

    monitor.stop_background_polling()
    os.makedirs('results', exist_ok=True)
    monitor.save_to_csv('results/integration_demo_log.csv')

    print("\n[Member2] Data saved → hand off to Member 4 for evaluation")
    print("\n✓ Integration demo complete")

    print("\n\n── How to use with real Mininet ──────────────────────────")
    print("Replace: ResourceMonitor(simulated=True)")
    print("With:    ResourceMonitor(hosts=net.hosts, simulated=False)")
    print("Everything else stays the same.")
