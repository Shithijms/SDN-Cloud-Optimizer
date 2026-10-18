"""
api.py
------
HTTP API wrapper around AVROScheduler.
Exposes scheduling as a REST endpoint so Ryu controller
(Member 1) can call it directly.

Run: python src/scheduler/api.py
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import time
import sys
import os
import threading

import urllib.request

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '../..')))

from .avro        import AVROScheduler
from .round_robin import RoundRobinScheduler
from .baselines   import LeastLoadedScheduler


# Active scheduler — swap this to compare algorithms
ACTIVE_SCHEDULER = AVROScheduler(pop_size=10, max_iter=30, threshold=0.3)

# Decision log — Member 4 reads this
decision_log = []
active_task_reservations = {}
reservation_lock = threading.Lock()


def apply_task_reservations(vm_stats_list, task):
    now = time.monotonic()
    effective_vms = [dict(vm) for vm in vm_stats_list]
    duration = max(0.0, float(task.get('duration', 0.0))) if task else 0.0
    cpu_demand = max(0.0, float(task.get('cpu_demand', 0.0))) if task else 0.0
    mem_demand = max(0.0, float(task.get('mem_demand', 0.0))) if task else 0.0

    with reservation_lock:
        for vm_id, vm in enumerate(effective_vms):
            active = [reservation for reservation in active_task_reservations.get(vm_id, [])
                      if reservation['expires_at'] > now]
            active_task_reservations[vm_id] = active
            vm['cpu'] = min(0.98, float(vm['cpu']) + sum(r['cpu_demand'] for r in active))
            vm['memory'] = min(0.98, float(vm['memory']) + sum(r['mem_demand'] for r in active))
            vm['queue_length'] = int(vm.get('queue_length', 0)) + len(active)

    return effective_vms, duration, cpu_demand, mem_demand


class SchedulerHandler(BaseHTTPRequestHandler):

    def do_POST(self):
        if self.path == '/api/schedule':
            self._handle_schedule()
        else:
            self._send_404()

    def do_GET(self):
        if self.path == '/api/log':
            self._handle_log()
        elif self.path == '/api/status':
            self._handle_status()
        else:
            self._send_404()

    def _handle_schedule(self):
        content_length = int(self.headers['Content-Length'])
        body           = self.rfile.read(content_length)
        request_body = json.loads(body)
        if isinstance(request_body, dict):
            vm_stats_list = request_body.get('vms', [])
            task = request_body.get('task', {})
        else:
            vm_stats_list = request_body
            task = {}
        if not vm_stats_list:
            self.send_error(400, 'vm_stats must contain at least one VM')
            return

        effective_vms, duration, cpu_demand, mem_demand = apply_task_reservations(
            vm_stats_list, task)

        start_time     = time.time()
        selected_vm_id = ACTIVE_SCHEDULER.select_vm(effective_vms)
        decision_ms    = (time.time() - start_time) * 1000

        from .fitness import compute_fitness
        fitness = compute_fitness(effective_vms[selected_vm_id])

        if duration > 0:
            with reservation_lock:
                active_task_reservations.setdefault(selected_vm_id, []).append({
                    'expires_at': time.monotonic() + duration,
                    'cpu_demand': cpu_demand,
                    'mem_demand': mem_demand,
                    'task_id': task.get('task_id'),
                    'profile': task.get('profile', 'unspecified'),
                })

        notify_success = self._notify_task_assigned(selected_vm_id) 

        response = {
            'selected_vm_id': selected_vm_id,
            'fitness_score':  round(fitness, 4),
            'decision_ms':    round(decision_ms, 2),
            'task_profile': task.get('profile'),
            'task_cpu_demand': cpu_demand,
            'task_mem_demand': mem_demand,
            'task_duration': duration,
            'effective_vm_stats': effective_vms[selected_vm_id],
            'timestamp':      time.time(),
        }

        decision_log.append({**response, 'vm_stats': effective_vms})

        # Log slow decisions
        if decision_ms > 50:
            print(f"  SLOW decision: {decision_ms:.1f}ms for VM{selected_vm_id}")
        else:
            print(f"  [{time.strftime('%H:%M:%S')}] "
                f"VM{selected_vm_id} selected for {task.get('profile', 'task')} "
                  f"(fitness={fitness:.3f}, {decision_ms:.1f}ms)")

        self._send_json(response)
    def _notify_task_assigned(self, vm_id: int) -> bool:
        """
        Tell Member 2's monitor that a task was assigned.
        Returns True if notification succeeded.
        """
        try:
            data = json.dumps({'vm_id': vm_id}).encode()
            req  = urllib.request.Request(
                'http://localhost:6000/api/task_assigned',
                data=data,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            urllib.request.urlopen(req, timeout=1.0)
            return True
        except Exception as e:
            print(f"  WARNING: task_assigned notify failed: {e}")
            return False
        

    def _handle_log(self):
        """Member 4 calls this to get decision history"""
        self._send_json(decision_log)

    def _handle_status(self):
        """Health check"""
        self._send_json({
            'status':    'running',
            'scheduler': type(ACTIVE_SCHEDULER).__name__,
            'decisions': len(decision_log),
        })

    def _send_json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def _send_404(self):
        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        # Suppress default HTTP logging noise
        pass


def run(host='0.0.0.0', port=5000):
    server = HTTPServer((host, port), SchedulerHandler)
    print(f"  Scheduler API running on http://{host}:{port}")
    print(f"  Active algorithm: {type(ACTIVE_SCHEDULER).__name__}")
    print(f"  Endpoints:")
    print(f"    POST /api/schedule  ← Member 2 sends vm_stats")
    print(f"    GET  /api/log       ← Member 4 reads decisions")
    print(f"    GET  /api/status    ← health check")
    print(f"\n  Waiting for requests...")
    server.serve_forever()


if __name__ == '__main__':
    run()