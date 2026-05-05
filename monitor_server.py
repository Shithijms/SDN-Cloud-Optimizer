"""
monitor_server.py
-----------------
HTTP server wrapping Member 2's ResourceMonitor.
Exposes VM stats to Member 3's connector.py via REST API.

Run: python monitor_server.py
Runs on: http://0.0.0.0:6000

Endpoints:
  GET  /api/vm_stats        → returns current VM stats list
  POST /api/task_assigned   → body: {"vm_id": 3}
  POST /api/task_completed  → body: {"vm_id": 3}
  GET  /api/status          → health check
"""

import sys
import os
import json
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from src.monitor.resource_monitor import ResourceMonitor

# ── Configuration ────────────────────────────────────────────────
PORT      = 6000
SIMULATED = True   # ← flip to False when Mininet is running

# ── Shared monitor instance ──────────────────────────────────────
monitor = ResourceMonitor(simulated=SIMULATED)
monitor.start_background_polling(interval=1)

print(f"  ResourceMonitor started (simulated={SIMULATED})")


class MonitorHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == '/api/vm_stats':
            self._handle_vm_stats()
        elif self.path == '/api/status':
            self._handle_status()
        else:
            self._send_404()

    def do_POST(self):
        if self.path == '/api/task_assigned':
            self._handle_task_assigned()
        elif self.path == '/api/task_completed':
            self._handle_task_completed()
        else:
            self._send_404()

    def _handle_vm_stats(self):
        """Return current VM stats — called by Member 3's connector"""
        stats = monitor.get_all_vm_stats()
        self._send_json(stats)

    def _handle_status(self):
        self._send_json({
            'status':    'running',
            'simulated': SIMULATED,
            'num_vms':   monitor.num_vms,
            'timestamp': time.time(),
        })

    def _handle_task_assigned(self):
        """
        Member 3 calls this after AVRO picks a VM.
        Updates queue_length so next stats fetch is accurate.
        """
        data   = self._read_json()
        vm_id  = data.get('vm_id')

        if vm_id is None:
            self._send_error("Missing vm_id in request body")
            return

        monitor.task_assigned(int(vm_id))
        self._send_json({
            'status': 'ok',
            'vm_id':  vm_id,
            'queue':  monitor._queues[int(vm_id)],
        })

    def _handle_task_completed(self):
        """
        Member 1 calls this when a flow finishes.
        Decrements queue on the VM that handled the task.
        """
        data  = self._read_json()
        vm_id = data.get('vm_id')

        if vm_id is None:
            self._send_error("Missing vm_id in request body")
            return

        monitor.task_completed(int(vm_id))
        self._send_json({
            'status': 'ok',
            'vm_id':  vm_id,
            'queue':  monitor._queues[int(vm_id)],
        })

    def _read_json(self) -> dict:
        length = int(self.headers.get('Content-Length', 0))
        body   = self.rfile.read(length)
        return json.loads(body)

    def _send_json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, message):
        body = json.dumps({'error': message}).encode()
        self.send_response(400)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def _send_404(self):
        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        # Clean logging — only show meaningful requests
        if '200' in str(args):
            print(f"  [{time.strftime('%H:%M:%S')}] "
                  f"{args[0].split()[0]} {args[0].split()[1]}")


def main():
    print("\n" + "="*55)
    print("  MONITOR SERVER — Member 2 API")
    print("="*55)
    print(f"  Port:      {PORT}")
    print(f"  Mode:      {'SIMULATED' if SIMULATED else 'LIVE MININET'}")
    print(f"  Endpoints:")
    print(f"    GET  /api/vm_stats       ← Member 3 fetches stats")
    print(f"    POST /api/task_assigned  ← Member 3 notifies assignment")
    print(f"    POST /api/task_completed ← Member 1 notifies completion")
    print(f"    GET  /api/status         ← health check")
    print(f"\n  Waiting for requests...")
    print("="*55)

    server = HTTPServer(('0.0.0.0', PORT), MonitorHandler)
    server.serve_forever()


if __name__ == '__main__':
    main()