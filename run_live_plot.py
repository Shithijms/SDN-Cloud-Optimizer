#!/usr/bin/env python3
"""Start/reuse the SDN services, run a live Mininet capture, and clean up."""

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
VENV = ROOT / '.venv' / 'bin'
STATS_FILE = Path('/tmp/cloud_host_stats.json')
RYU_HEALTH = 'http://127.0.0.1:8080/cloud/health'
RYU_STATS = 'http://127.0.0.1:8080/cloud/stats'
AVRO_STATUS = 'http://127.0.0.1:5000/api/status'


def port_open(port):
    with socket.socket() as sock:
        sock.settimeout(0.4)
        return sock.connect_ex(('127.0.0.1', port)) == 0


def check_plot_dependencies():
    try:
        import matplotlib  # noqa: F401
        import numpy  # noqa: F401
        import requests as requests_module  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            f'Missing Python dependency: {exc.name}. Install before starting Mininet: '
            '.venv/bin/python -m pip install -r requirements.txt'
        ) from exc


def check_scheduler_sources():
    conflicted = []
    for relative_path in ('src/scheduler/avro.py', 'src/scheduler/api.py'):
        source_path = ROOT / relative_path
        try:
            source = source_path.read_text()
        except OSError as exc:
            raise RuntimeError(f'Cannot read scheduler source {relative_path}: {exc}') from exc
        if any(marker in source for marker in ('<<<<<<<', '=======', '>>>>>>>')):
            conflicted.append(relative_path)
    if conflicted:
        raise RuntimeError(
            'Resolve the existing Git conflict markers before running: '
            + ', '.join(conflicted)
        )


def healthy(url):
    try:
        response = requests.get(url, timeout=2)
        return response.ok
    except requests.RequestException:
        return False


def wait_for(check, description, timeout, process=None):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            print(f'{description}: ready', flush=True)
            return
        if process is not None and process.poll() is not None:
            raise RuntimeError(f'{description} exited early with code {process.returncode}')
        time.sleep(1)
    raise RuntimeError(f'Timed out waiting for {description}')


def fresh_stats_and_switches():
    try:
        response = requests.get(RYU_STATS, timeout=3)
        response.raise_for_status()
        payload = response.json()
        host_stats = payload.get('host_stats', {})
        timestamp = host_stats.get('_timestamp')
        fresh = timestamp is not None and time.time() - timestamp < 10
        hosts = [key for key in host_stats if key.startswith('h')]
        switches = len(payload.get('switches', {}))
        return fresh and len(hosts) == 8 and switches >= 7
    except (requests.RequestException, ValueError):
        return False


def topology_processes_present():
    try:
        output = subprocess.check_output(['pgrep', '-af', 'cloud_topology.py'],
                                         text=True)
    except subprocess.CalledProcessError:
        return False
    return any('cloud_topology.py' in line and 'pgrep -af' not in line
               for line in output.splitlines())


def stop_process(process, name):
    if process is None or process.poll() is not None:
        return
    print(f'Stopping {name}...', flush=True)
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', type=int, default=100)
    parser.add_argument('--interval', type=float, default=1.0)
    parser.add_argument('--source-ip', default='10.0.0.1',
                        help='source host IP in the Mininet topology')
    parser.add_argument('--vms', type=int, choices=(4,), default=4,
                        help='number of live Tenant A VMs to graph (currently h1-h4)')
    parser.add_argument('--no-cleanup', action='store_true',
                        help='leave services started by this script running')
    parser.add_argument('--skip-mininet', action='store_true',
                        help='reuse an already-running Mininet topology and its fresh stats')
    args = parser.parse_args()
    if args.samples < 1 or args.interval < 0:
        parser.error('--samples must be positive and --interval non-negative')
    if os.geteuid() != 0:
        parser.error('Run with sudo: sudo .venv/bin/python run_live_plot.py')

    try:
        check_scheduler_sources()
    except RuntimeError as exc:
        parser.error(str(exc))

    try:
        check_plot_dependencies()
    except RuntimeError as exc:
        parser.error(str(exc))

    children = []
    started = {}
    try:
        print('Live plot scope: 4 VMs (Tenant A hosts h1-h4); topology remains 8 hosts.', flush=True)
        if not args.skip_mininet:
            if topology_processes_present():
                raise RuntimeError('A Mininet topology already appears active. Use --skip-mininet or stop it first.')
            print('Cleaning stale Mininet state before starting Ryu...', flush=True)
            cleanup = subprocess.run(['mn', '-c'], check=False)
            if cleanup.returncode:
                raise RuntimeError(f'mn -c failed with exit code {cleanup.returncode}')

        if healthy(RYU_HEALTH):
            print('Reusing healthy Ryu controller.', flush=True)
        else:
            if port_open(8080) or port_open(6633):
                raise RuntimeError('A controller port is occupied but Ryu health is failing.')
            cmd = [str(VENV / 'ryu-manager'), 'controller/cloud_controller.py',
                   '--ofp-tcp-listen-port', '6633']
            process = subprocess.Popen(cmd, cwd=ROOT)
            children.append((process, 'Ryu'))
            started['ryu'] = process
            wait_for(lambda: healthy(RYU_HEALTH), 'Ryu REST API', 45, process)

        if healthy(AVRO_STATUS):
            print('Reusing healthy AVRO scheduler.', flush=True)
        else:
            if port_open(5000):
                raise RuntimeError('Port 5000 is occupied but the AVRO status endpoint failed.')
            process = subprocess.Popen(
                [str(VENV / 'python'), '-m', 'src.scheduler.api'], cwd=ROOT)
            children.append((process, 'AVRO scheduler'))
            started['avro'] = process
            wait_for(lambda: healthy(AVRO_STATUS), 'AVRO scheduler API', 30, process)

        if healthy('http://127.0.0.1:9000/'):
            print('Reusing healthy experiment API.', flush=True)
        else:
            if port_open(9000):
                raise RuntimeError('Port 9000 is occupied but the experiment API is unhealthy.')
            process = subprocess.Popen([str(VENV / 'python'), 'experiment_api.py'], cwd=ROOT)
            children.append((process, 'experiment API'))
            started['experiment'] = process
            wait_for(lambda: healthy('http://127.0.0.1:9000/'), 'experiment API', 30, process)

        if args.skip_mininet:
            if not topology_processes_present() or not fresh_stats_and_switches():
                raise RuntimeError('--skip-mininet requested but fresh 8-host/7-switch stats are unavailable.')
            print('Reusing existing Mininet topology.', flush=True)
        else:
            process = subprocess.Popen(
                ['python3', str(ROOT / 'cloud_topology.py'), '--no-cli', '--cpu-load'], cwd=ROOT)
            children.append((process, 'Mininet topology'))
            started['mininet'] = process
            wait_for(fresh_stats_and_switches, '8 live Mininet hosts and 7 Ryu switches', 90, process)

        plot_cmd = [str(VENV / 'python'), 'results/plot_convergence.py',
                    '--samples', str(args.samples), '--interval', str(args.interval),
                    '--source-ip', args.source_ip]
        subprocess.run(plot_cmd, cwd=ROOT, check=True)
    except KeyboardInterrupt:
        print('\nInterrupted; cleaning up services started by this script.', flush=True)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f'Live plot run failed: {exc}', file=sys.stderr)
        return 1
    finally:
        if not args.no_cleanup:
            if started.get('mininet') is not None:
                stop_process(started['mininet'], 'Mininet topology')
                subprocess.run(['mn', '-c'], check=False)
            for process, name in reversed(children):
                if name != 'Mininet topology':
                    stop_process(process, name)
        else:
            print('Leaving services running (--no-cleanup).', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
