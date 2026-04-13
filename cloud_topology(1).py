#!/usr/bin/env python3
"""
Cloud Network Topology Simulator
=================================
Simulates a 3-tier data center cloud environment:
  - Core switch (1)
  - Aggregation switches (2) — one per tenant
  - Edge switches (4) — two per tenant
  - Hosts (8) — VMs across subnets

Tenant A: 10.0.1.x  (hosts h1, h2, h3, h4)
Tenant B: 10.0.2.x  (hosts h5, h6, h7, h8)
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


def collect_host_stats(net):
    """Continuously collect CPU and memory stats from all hosts."""
    global RUNNING
    while RUNNING:
        stats = {}
        for host in net.hosts:
            try:
                cpu_cmd = host.cmd("grep 'cpu ' /proc/stat")
                mem_cmd = host.cmd("cat /proc/meminfo | grep -E 'MemTotal|MemAvailable'")
                bw_cmd  = host.cmd("cat /proc/net/dev")

                # Parse CPU
                cpu_vals = cpu_cmd.strip().split()[1:5]
                if len(cpu_vals) == 4:
                    total   = sum(int(x) for x in cpu_vals)
                    idle    = int(cpu_vals[3])
                    cpu_pct = round((1 - idle / max(total, 1)) * 100, 1)
                else:
                    cpu_pct = 0.0

                # Parse Memory
                mem_total = mem_avail = 0
                for line in mem_cmd.strip().split('\n'):
                    parts = line.split()
                    if len(parts) >= 2:
                        if 'MemTotal' in parts[0]:
                            mem_total = int(parts[1])
                        elif 'MemAvailable' in parts[0]:
                            mem_avail = int(parts[1])
                mem_pct = round((1 - mem_avail / max(mem_total, 1)) * 100, 1) if mem_total else 0.0

                # Parse Network RX/TX bytes
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

                stats[host.name] = {
                    'cpu'     : cpu_pct,
                    'mem'     : mem_pct,
                    'rx_bytes': rx_bytes,
                    'tx_bytes': tx_bytes,
                    'ip'      : host.IP(),
                    'tenant'  : 'A' if host.name in ['h1','h2','h3','h4'] else 'B'
                }
            except Exception:
                stats[host.name] = {
                    'cpu': 0, 'mem': 0,
                    'rx_bytes': 0, 'tx_bytes': 0,
                    'ip': host.IP(),
                    'tenant': 'A' if host.name in ['h1','h2','h3','h4'] else 'B'
                }

        stats['_timestamp'] = time.time()
        with open(MONITOR_FILE, 'w') as f:
            json.dump(stats, f)
        time.sleep(3)


def build_cloud_topology():
    setLogLevel('info')
    net = Mininet(
        controller=RemoteController,
        switch=OVSSwitch,
        link=TCLink,
        autoSetMacs=True
    )

    info('*** Adding Remote Ryu Controller\n')
    c0 = net.addController('c0', controller=RemoteController,
                           ip='127.0.0.1', port=6633)

    info('*** Building 3-Tier Data Center Topology\n')

    # Core Layer
    core = net.addSwitch('s1', cls=OVSSwitch, protocols='OpenFlow13')

    # Aggregation Layer
    agg_a = net.addSwitch('s2', cls=OVSSwitch, protocols='OpenFlow13')
    agg_b = net.addSwitch('s3', cls=OVSSwitch, protocols='OpenFlow13')

    # Edge Layer
    edge_a1 = net.addSwitch('s4', cls=OVSSwitch, protocols='OpenFlow13')
    edge_a2 = net.addSwitch('s5', cls=OVSSwitch, protocols='OpenFlow13')
    edge_b1 = net.addSwitch('s6', cls=OVSSwitch, protocols='OpenFlow13')
    edge_b2 = net.addSwitch('s7', cls=OVSSwitch, protocols='OpenFlow13')

    # Tenant A VMs — subnet 10.0.1.0/24
    h1 = net.addHost('h1', ip='10.0.1.1/24')
    h2 = net.addHost('h2', ip='10.0.1.2/24')
    h3 = net.addHost('h3', ip='10.0.1.3/24')
    h4 = net.addHost('h4', ip='10.0.1.4/24')

    # Tenant B VMs — subnet 10.0.2.0/24
    h5 = net.addHost('h5', ip='10.0.2.1/24')
    h6 = net.addHost('h6', ip='10.0.2.2/24')
    h7 = net.addHost('h7', ip='10.0.2.3/24')
    h8 = net.addHost('h8', ip='10.0.2.4/24')

    info('*** Adding links with bandwidth constraints\n')

    # Core <-> Aggregation (1 Gbps backbone)
    net.addLink(core,  agg_a,   bw=1000, delay='1ms')
    net.addLink(core,  agg_b,   bw=1000, delay='1ms')

    # Aggregation <-> Edge (100 Mbps)
    net.addLink(agg_a, edge_a1, bw=100,  delay='2ms')
    net.addLink(agg_a, edge_a2, bw=100,  delay='2ms')
    net.addLink(agg_b, edge_b1, bw=100,  delay='2ms')
    net.addLink(agg_b, edge_b2, bw=100,  delay='2ms')

    # Edge <-> Hosts (access links)
    net.addLink(edge_a1, h1, bw=100, delay='0.5ms')
    net.addLink(edge_a1, h2, bw=100, delay='0.5ms')
    net.addLink(edge_a2, h3, bw=100, delay='0.5ms')
    net.addLink(edge_a2, h4, bw=100, delay='0.5ms')
    net.addLink(edge_b1, h5, bw=100, delay='0.5ms')
    net.addLink(edge_b1, h6, bw=100, delay='0.5ms')
    net.addLink(edge_b2, h7, bw=100, delay='0.5ms')
    net.addLink(edge_b2, h8, bw=100, delay='0.5ms')

    info('*** Starting network\n')
    net.build()
    c0.start()
    for sw in [core, agg_a, agg_b, edge_a1, edge_a2, edge_b1, edge_b2]:
        sw.start([c0])

    info('\n=== Cloud Topology Ready ===\n')
    info('Tenant A: h1(10.0.1.1) h2(10.0.1.2) h3(10.0.1.3) h4(10.0.1.4)\n')
    info('Tenant B: h5(10.0.2.1) h6(10.0.2.2) h7(10.0.2.3) h8(10.0.2.4)\n')
    info('Dashboard: http://localhost:9000\n')
    info('\nUseful CLI commands:\n')
    info('  pingall                   - test all connectivity\n')
    info('  h1 ping -c3 h2            - ping within Tenant A\n')
    info('  h1 ping -c3 h5            - cross-tenant ping\n')
    info('  iperf h1 h2               - bandwidth test\n\n')

    # Start monitoring thread
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
