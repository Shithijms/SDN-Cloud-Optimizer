"""
Member 2 - Resource Monitoring Module
Collects real-time CPU, memory, queue length, and network delay
from Mininet hosts (VMs) and feeds data to AVRO scheduler.
"""

import time
import subprocess
import threading
import csv
import os
import random

# ─── VM Stats Data Contract (agreed with all team members) ───────────────────
# {
#   'vm_id':        int    - index 0,1,2...
#   'cpu':          float  - 0.0 to 1.0
#   'memory':       float  - 0.0 to 1.0
#   'queue_length': int    - tasks currently waiting
#   'delay':        float  - milliseconds
#   'timestamp':    float  - Unix time
# }
# ─────────────────────────────────────────────────────────────────────────────

class ResourceMonitor:
    """
    Monitors real-time resource stats for all VM hosts in the Mininet topology.
    Works in two modes:
      - LIVE: uses actual Mininet host objects (for real Mininet runs)
      - SIMULATED: generates realistic fake stats (for testing without Mininet)
    """

    def __init__(self, hosts=None, simulated=False):
        """
        hosts     : list of Mininet host objects (pass None if simulated=True)
        simulated : if True, runs without Mininet (for testing)
        """
        self.hosts = hosts or []
        self.simulated = simulated
        self.num_vms = len(self.hosts) if self.hosts else 4

        # Queue tracking — incremented/decremented by scheduler
        self._queues = [0] * self.num_vms

        # History log for CSV export
        self.history = []

        # Background polling thread
        self._running = False
        self._poll_interval = 2  # seconds
        self._latest_stats = []
        self._lock = threading.Lock()

        # Simulated VM state (drifts over time for realistic behaviour)
        self._sim_cpu    = [random.uniform(0.1, 0.4) for _ in range(self.num_vms)]
        self._sim_mem    = [random.uniform(0.2, 0.5) for _ in range(self.num_vms)]
        self._sim_delay  = [random.uniform(2.0, 15.0) for _ in range(self.num_vms)]

    # ── Public API ────────────────────────────────────────────────────────────

    def get_all_vm_stats(self):
        """
        Returns a list of VM stat dicts for ALL hosts.
        This is the main method called by the AVRO scheduler.
        """
        if self.simulated:
            stats = [self._get_simulated_stats(i) for i in range(self.num_vms)]
        else:
            stats = [self._get_live_stats(i) for i in range(len(self.hosts))]

        self.history.append({'snapshot_time': time.time(), 'vms': stats})
        return stats

    def get_vm_stats(self, vm_id):
        """Returns stats for a single VM by index."""
        all_stats = self.get_all_vm_stats()
        return all_stats[vm_id]

    def task_assigned(self, vm_id):
        """Call this when a task is sent to a VM (increments queue)."""
        self._queues[vm_id] += 1

    def task_completed(self, vm_id):
        """Call this when a VM finishes a task (decrements queue)."""
        self._queues[vm_id] = max(0, self._queues[vm_id] - 1)

    def start_background_polling(self, interval=2):
        """
        Starts a background thread that polls stats continuously.
        Other modules can read self._latest_stats at any time.
        """
        self._poll_interval = interval
        self._running = True
        t = threading.Thread(target=self._poll_loop, daemon=True)
        t.start()
        print(f"[Monitor] Background polling started (every {interval}s)")

    def stop_background_polling(self):
        self._running = False
        print("[Monitor] Background polling stopped")

    def get_latest_stats(self):
        """Thread-safe read of the latest polled stats."""
        with self._lock:
            return list(self._latest_stats)

    def save_to_csv(self, filepath=None):
        if filepath is None:
            root     = os.path.abspath(
                os.path.join(os.path.dirname(__file__), '..', '..'))
            filepath = os.path.join(root, 'results', 'monitoring_log.csv')

        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)

        rows = []
        for snapshot in self.history:
            for vm in snapshot['vms']:
                rows.append({
                    'snapshot_time': snapshot['snapshot_time'],
                    **vm
                })
        if not rows:
            print("[Monitor] No data to save.")
            return

        with open(filepath, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        print(f"[Monitor] Saved {len(rows)} records to {filepath}")


    def print_stats_table(self, stats):
        """Pretty-print a stats snapshot to terminal."""
        print(f"\n{'VM':<6} {'CPU%':<8} {'MEM%':<8} {'Queue':<8} {'Delay(ms)':<12}")
        print("-" * 45)
        for vm in stats:
            print(f"VM{vm['vm_id']:<5} "
                  f"{vm['cpu']*100:>5.1f}%   "
                  f"{vm['memory']*100:>5.1f}%   "
                  f"{vm['queue_length']:>5}    "
                  f"{vm['delay']:>8.1f}ms")

    # ── Internal methods ──────────────────────────────────────────────────────

    def _get_live_stats(self, idx):
        """Reads stats from an actual Mininet host."""
        host = self.hosts[idx]
        cpu    = self._read_host_cpu(host)
        memory = self._read_host_memory(host)
        delay  = self._ping_host(host)
        return {
            'vm_id':        idx,
            'cpu':          cpu,
            'memory':       memory,
            'queue_length': self._queues[idx],
            'delay':        delay,
            'timestamp':    time.time()
        }

    def _read_host_cpu(self, host):
        """Read CPU usage of a Mininet host via /proc/stat."""
        try:
            # Run command inside the Mininet host's namespace
            out = host.cmd('cat /proc/stat | head -1')
            parts = out.split()
            # user, nice, system, idle, iowait, irq, softirq
            vals = [int(x) for x in parts[1:8]]
            idle  = vals[3]
            total = sum(vals)
            # Second reading after small delay for delta
            time.sleep(0.1)
            out2 = host.cmd('cat /proc/stat | head -1')
            parts2 = out2.split()
            vals2  = [int(x) for x in parts2[1:8]]
            idle2  = vals2[3]
            total2 = sum(vals2)
            cpu_usage = 1.0 - (idle2 - idle) / max((total2 - total), 1)
            return max(0.0, min(1.0, cpu_usage))
        except Exception:
            return random.uniform(0.1, 0.6)   # fallback

    def _read_host_memory(self, host):
        """Read memory usage from Mininet host via /proc/meminfo."""
        try:
            out = host.cmd('cat /proc/meminfo')
            info = {}
            for line in out.strip().split('\n'):
                parts = line.split()
                if len(parts) >= 2:
                    info[parts[0].rstrip(':')] = int(parts[1])
            total     = info.get('MemTotal', 1)
            available = info.get('MemAvailable', info.get('MemFree', 0))
            return max(0.0, min(1.0, 1.0 - available / total))
        except Exception:
            return random.uniform(0.2, 0.5)   # fallback

    def _ping_host(self, host):
        """Ping a Mininet host and return RTT in ms."""
        try:
            result = subprocess.run(
                ['ping', '-c', '1', '-W', '1', host.IP()],
                capture_output=True, text=True, timeout=2
            )
            for line in result.stdout.split('\n'):
                if 'time=' in line:
                    return float(line.split('time=')[1].split(' ')[0])
        except Exception:
            pass
        return 5.0   # fallback: 5ms

    def _get_simulated_stats(self, idx):
        """
        Generates realistic drifting stats for testing without Mininet.
        CPU/memory drift over time to simulate real load changes.
        """
        # Drift CPU slightly each call (±5%)
        self._sim_cpu[idx] += random.uniform(-0.05, 0.07)
        self._sim_cpu[idx]  = max(0.05, min(0.95, self._sim_cpu[idx]))

        # Drift memory more slowly (±2%)
        self._sim_mem[idx] += random.uniform(-0.02, 0.03)
        self._sim_mem[idx]  = max(0.10, min(0.90, self._sim_mem[idx]))

        # Drift delay (±2ms)
        self._sim_delay[idx] += random.uniform(-2, 2)
        self._sim_delay[idx]  = max(1.0, min(50.0, self._sim_delay[idx]))

        # Add extra load if queue is long
        cpu_boost = min(0.3, self._queues[idx] * 0.05)

        return {
            'vm_id':        idx,
            'cpu':          min(1.0, self._sim_cpu[idx] + cpu_boost),
            'memory':       self._sim_mem[idx],
            'queue_length': self._queues[idx],
            'delay':        self._sim_delay[idx],
            'timestamp':    time.time()
        }

    def _poll_loop(self):
        """Background polling loop."""
        while self._running:
            stats = self.get_all_vm_stats()
            with self._lock:
                self._latest_stats = stats
            time.sleep(self._poll_interval)
