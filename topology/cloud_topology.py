#!/usr/bin/env python3
"""
Cloud Network Topology Simulator – Single subnet 10.0.0.0/24
Tenant A: h1..h4 (10.0.0.1-4)
Tenant B: h5..h8 (10.0.0.5-8)

KEY CHANGE: collect_host_stats() now reads /proc/<pid>/stat per host.
This gives real per-VM CPU usage instead of shared system-wide stats.
Everything else is identical to the original.
"""

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info
from mininet.link import TCLink
import time
import threading
import json
import signal

MONITOR_FILE = '/tmp/cloud_host_stats.json'
RUNNING = True

def signal_handler(sig, frame):
    global RUNNING
    RUNNING = False

signal.signal(signal.SIGINT, signal_handler)

# ── Per-PID CPU reader ────────────────────────────────────────────────────────
def _read_pid_cpu(pid):
    """
    Read CPU usage for a PID and ALL its descendants.
    Needed because stress forks child workers — the shell PID
    itself shows 0% but its children consume the actual CPU.
    """
    def get_all_pids(root_pid):
        """Walk process tree and collect all descendant PIDs."""
        pids = [root_pid]
        try:
            children_file = f'/proc/{root_pid}/task/{root_pid}/children'
            with open(children_file, 'r') as f:
                children = f.read().split()
            for child_pid in children:
                pids.extend(get_all_pids(int(child_pid)))
        except Exception:
            pass
        return pids

    def read_tree_ticks(root_pid):
        """Sum utime+stime across all PIDs in the tree."""
        all_pids = get_all_pids(root_pid)
        total_proc_ticks = 0
        for p in all_pids:
            try:
                with open(f'/proc/{p}/stat', 'r') as f:
                    fields = f.read().split()
                total_proc_ticks += int(fields[13]) + int(fields[14])
            except Exception:
                pass
        # Total system ticks for percentage
        with open('/proc/stat', 'r') as f:
            cpu_fields = f.readline().split()[1:]
        total_ticks = sum(int(x) for x in cpu_fields)
        return total_proc_ticks, total_ticks

    try:
        t1_proc, t1_total = read_tree_ticks(pid)
        time.sleep(0.5)
        t2_proc, t2_total = read_tree_ticks(pid)

        proc_delta  = t2_proc  - t1_proc
        total_delta = t2_total - t1_total

        if total_delta <= 0:
            return 0.0

        return round(min(100.0 * proc_delta / total_delta, 100.0), 1)
    except Exception:
        return 0.0
    

def _read_host_memory():
    """
    Read system memory from /proc/meminfo.
    Returns memory usage percentage 0.0 - 100.0
    """
    try:
        mem_total = mem_avail = 0
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                parts = line.split()
                if parts[0] == 'MemTotal:':
                    mem_total = int(parts[1])
                elif parts[0] == 'MemAvailable:':
                    mem_avail = int(parts[1])
        if mem_total == 0:
            return 0.0
        return round((1 - mem_avail / mem_total) * 100, 1)
    except Exception:
        return 0.0


def _read_host_network(host):
    """
    Read RX/TX bytes from host's own network namespace via /proc/net/dev.
    Each Mininet host has its own namespace so this IS per-VM accurate.
    Returns (rx_bytes, tx_bytes)
    """
    try:
        bw_cmd = host.cmd("cat /proc/net/dev")
        rx_bytes = tx_bytes = 0
        for line in bw_cmd.strip().split('\n'):
            if 'lo' in line or 'Inter' in line or 'face' in line:
                continue
            parts = line.strip().split()
            if len(parts) >= 10:
                try:
                    rx_bytes += int(parts[1])
                    tx_bytes += int(parts[9])
                except (ValueError, IndexError):
                    pass
        return rx_bytes, tx_bytes
    except Exception:
        return 0, 0


# ── Main stats collector ──────────────────────────────────────────────────────
def collect_host_stats(net):
    """
    Continuously collect per-VM stats and write to MONITOR_FILE.
    CPU is read from /proc/<pid>/stat — real per-process usage.
    Network is read from each host's own network namespace.
    """
    global RUNNING

    # Build PID map once at startup
    pid_map = {}
    for host in net.hosts:
        pid = host.pid
        if pid:
            pid_map[host.name] = pid
            info(f'[Monitor] {host.name} -> PID {pid}\n')
        else:
            info(f'[Monitor] WARNING: {host.name} has no PID\n')

    while RUNNING:
        stats = {}
        mem_pct = _read_host_memory()

        for host in net.hosts:
            name = host.name
            pid  = pid_map.get(name)

            cpu_pct = _read_pid_cpu(pid) if pid else 0.0
            rx_bytes, tx_bytes = _read_host_network(host)

            stats[name] = {
                'cpu'     : cpu_pct,
                'mem'     : mem_pct,
                'rx_bytes': rx_bytes,
                'tx_bytes': tx_bytes,
                'ip'      : host.IP(),
                'tenant'  : 'A' if name in ['h1','h2','h3','h4'] else 'B',
            }

        stats['_timestamp'] = time.time()
        with open(MONITOR_FILE, 'w') as f:
            json.dump(stats, f)

        time.sleep(3)


# ── Topology builder ──────────────────────────────────────────────────────────
def build_cloud_topology():
    setLogLevel('info')
    net = Mininet(controller=None, switch=OVSSwitch, link=TCLink, autoSetMacs=True)

    info('*** Adding Remote Ryu Controller\n')
    c0 = net.addController('c0', controller=RemoteController,
                           ip='127.0.0.1', port=6633)

    info('*** Building 3-Tier Data Center Topology\n')

    core    = net.addSwitch('s1', protocols='OpenFlow13')
    agg_a   = net.addSwitch('s2', protocols='OpenFlow13')
    agg_b   = net.addSwitch('s3', protocols='OpenFlow13')
    edge_a1 = net.addSwitch('s4', protocols='OpenFlow13')
    edge_a2 = net.addSwitch('s5', protocols='OpenFlow13')
    edge_b1 = net.addSwitch('s6', protocols='OpenFlow13')
    edge_b2 = net.addSwitch('s7', protocols='OpenFlow13')

    # Tenant A (10.0.0.1-4)
    h1 = net.addHost('h1', ip='10.0.0.1/24')
    h2 = net.addHost('h2', ip='10.0.0.2/24')
    h3 = net.addHost('h3', ip='10.0.0.3/24')
    h4 = net.addHost('h4', ip='10.0.0.4/24')
    # Tenant B (10.0.0.5-8)
    h5 = net.addHost('h5', ip='10.0.0.5/24')
    h6 = net.addHost('h6', ip='10.0.0.6/24')
    h7 = net.addHost('h7', ip='10.0.0.7/24')
    h8 = net.addHost('h8', ip='10.0.0.8/24')

    info('*** Adding links with bandwidth constraints\n')
    net.addLink(core,    agg_a,   bw=1000, delay='1ms')
    net.addLink(core,    agg_b,   bw=1000, delay='1ms')
    net.addLink(agg_a,   edge_a1, bw=100,  delay='2ms')
    net.addLink(agg_a,   edge_a2, bw=100,  delay='2ms')
    net.addLink(agg_b,   edge_b1, bw=100,  delay='2ms')
    net.addLink(agg_b,   edge_b2, bw=100,  delay='2ms')
    net.addLink(edge_a1, h1,      bw=100,  delay='0.5ms')
    net.addLink(edge_a1, h2,      bw=100,  delay='0.5ms')
    net.addLink(edge_a2, h3,      bw=100,  delay='0.5ms')
    net.addLink(edge_a2, h4,      bw=100,  delay='0.5ms')
    net.addLink(edge_b1, h5,      bw=100,  delay='0.5ms')
    net.addLink(edge_b1, h6,      bw=100,  delay='0.5ms')
    net.addLink(edge_b2, h7,      bw=100,  delay='0.5ms')
    net.addLink(edge_b2, h8,      bw=100,  delay='0.5ms')

    info('*** Starting network\n')
    net.build()
    c0.start()
    for sw in [core, agg_a, agg_b, edge_a1, edge_a2, edge_b1, edge_b2]:
        sw.start([c0])

    time.sleep(2)
    info('\n=== Cloud Topology Ready ===\n')
    info('Tenant A: h1(10.0.0.1) h2(10.0.0.2) h3(10.0.0.3) h4(10.0.0.4)\n')
    info('Tenant B: h5(10.0.0.5) h6(10.0.0.6) h7(10.0.0.7) h8(10.0.0.8)\n')
    info('\nUseful CLI commands:\n')
    info('  pingall\n')
    info('  h1 ping -c3 h2           within Tenant A\n')
    info('  h1 ping -c3 h5           cross-tenant (blocked)\n')
    info('  h1 stress --cpu 1 &      load h1 CPU\n')
    info('  h2 stress --cpu 1 &      load h2 CPU\n')
    info('  iperf h1 h2              bandwidth test\n\n')

    monitor_thread = threading.Thread(
        target=collect_host_stats, args=(net,), daemon=True)
    monitor_thread.start()
    info('*** Host stats monitor running -> /tmp/cloud_host_stats.json\n\n')

    CLI(net)

    global RUNNING
    RUNNING = False
    info('*** Stopping network\n')
    net.stop()


if __name__ == '__main__':
    build_cloud_topology()
