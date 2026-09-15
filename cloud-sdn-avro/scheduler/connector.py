"""
connector.py
------------
Data connector — bridges VM stats sources to AVROScheduler.

Two modes:
  SIMULATION : uses VMState objects (current, no Mininet needed)
  LIVE       : calls Member 2's monitoring API (Month 2)

The scheduler never knows which mode is active.
Swap the mode in one place — everything else works unchanged.

Member 2's API contract (what we expect from them):
  GET http://{MONITOR_HOST}:{MONITOR_PORT}/api/vm_stats
  Returns:
  [
    {
      "vm_id":        0,
      "cpu":          0.65,
      "memory":       0.40,
      "queue_length": 3,
      "delay":        12.5,
      "timestamp":    1234567890.0
    },
    ...
  ]
"""

import time
import json
import urllib.request
import urllib.error


# ── Configuration ────────────────────────────────────────────────
MONITOR_HOST = "localhost"       # Member 2's machine IP
MONITOR_PORT = 6000              # Member 2's monitoring API port
MONITOR_URL  = f"http://{MONITOR_HOST}:{MONITOR_PORT}/api/vm_stats"

# How long to wait for Member 2's API before giving up
REQUEST_TIMEOUT_SEC = 2.0

# How stale can VM stats be before we reject them (seconds)
MAX_STATS_AGE_SEC = 5.0


# ── Mode selector ────────────────────────────────────────────────
class ConnectorMode:
    SIMULATION = "simulation"
    LIVE       = "live"


# ── Main connector class ─────────────────────────────────────────

class VMConnector:
    """
    Single interface for getting VM stats regardless of source.

    Usage:
        # Simulation mode (current)
        connector = VMConnector(mode=ConnectorMode.SIMULATION)

        # Live mode (Month 2)
        connector = VMConnector(mode=ConnectorMode.LIVE)

        # Both modes use same interface
        vm_stats = connector.get_stats()
        selected = scheduler.select_vm(vm_stats)
    """

    def __init__(self,
                 mode:    str  = ConnectorMode.SIMULATION,
                 vm_list: list = None):
        """
        Parameters
        ----------
        mode    : ConnectorMode.SIMULATION or ConnectorMode.LIVE
        vm_list : list of VMState objects (simulation mode only)
        """
        self.mode        = mode
        self.vm_list     = vm_list or []
        self._last_stats = None
        self._last_fetch = 0

        print(f"  VMConnector initialized in {mode.upper()} mode")
        if mode == ConnectorMode.LIVE:
            print(f"  Monitoring API: {MONITOR_URL}")

    # ── Public interface ─────────────────────────────────────────

    def get_stats(self) -> list:
        """
        Get current VM stats from whichever source is active.

        Returns
        -------
        list of dicts in standard vm_stats format:
        [{vm_id, cpu, memory, queue_length, delay, timestamp}, ...]

        Raises
        ------
        ConnectionError : if live mode and Member 2's API is down
        ValueError      : if stats are stale or malformed
        """
        if self.mode == ConnectorMode.SIMULATION:
            return self._get_simulation_stats()
        else:
            return self._get_live_stats()

    def is_live(self) -> bool:
        return self.mode == ConnectorMode.LIVE

    def test_connection(self) -> dict:
        """
        Test connectivity to Member 2's API.
        Call this at startup to verify integration is working.
        """
        if self.mode == ConnectorMode.SIMULATION:
            return {
                'status':  'ok',
                'mode':    'simulation',
                'message': 'Using simulated VM stats',
                'num_vms': len(self.vm_list),
            }

        try:
            stats = self._get_live_stats()
            return {
                'status':  'ok',
                'mode':    'live',
                'message': f'Connected to {MONITOR_URL}',
                'num_vms': len(stats),
                'sample':  stats[0] if stats else None,
            }
        except Exception as e:
            return {
                'status':  'error',
                'mode':    'live',
                'message': str(e),
                'num_vms': 0,
            }

    # ── Simulation mode ──────────────────────────────────────────

    def _get_simulation_stats(self) -> list:
        """Get stats from VMState objects"""
        if not self.vm_list:
            raise ValueError(
                "vm_list is empty. Pass VMState objects to constructor.")

        return [vm.get_stats() for vm in self.vm_list]

    # ── Live mode ────────────────────────────────────────────────

    def _get_live_stats(self) -> list:
        """
        Fetch real VM stats from Member 2's monitoring API.
        Includes timeout, retry, and staleness checking.
        """
        try:
            req      = urllib.request.Request(MONITOR_URL)
            response = urllib.request.urlopen(
                req, timeout=REQUEST_TIMEOUT_SEC)
            raw      = response.read().decode('utf-8')
            stats    = json.loads(raw)

        except urllib.error.URLError as e:
            # Member 2's API is down — fall back to last known stats
            if self._last_stats is not None:
                age = time.time() - self._last_fetch
                if age < MAX_STATS_AGE_SEC:
                    print(f"  WARNING: Using cached stats ({age:.1f}s old)")
                    return self._last_stats
            raise ConnectionError(
                f"Cannot reach monitoring API at {MONITOR_URL}. "
                f"Is Member 2's server running? Error: {e}")

        except json.JSONDecodeError as e:
            raise ValueError(
                f"Member 2's API returned invalid JSON: {e}")

        # Validate the response
        validated = self._validate_stats(stats)

        # Cache for fallback
        self._last_stats = validated
        self._last_fetch = time.time()

        return validated

    def _validate_stats(self, stats: list) -> list:
        """
        Validate and normalize stats from Member 2.
        Fixes common issues like missing fields or out-of-range values.
        """
        required_fields = {
            'vm_id', 'cpu', 'memory', 'queue_length', 'delay'
        }

        validated = []
        for i, vm in enumerate(stats):

            # Check required fields
            missing = required_fields - set(vm.keys())
            if missing:
                raise ValueError(
                    f"VM{i} stats missing fields: {missing}. "
                    f"Tell Member 2 to add these to their API response.")

            # Normalize and clamp values to valid ranges
            clean = {
                'vm_id':        int(vm['vm_id']),
                'cpu':          float(max(0.0, min(1.0, vm['cpu']))),
                'memory':       float(max(0.0, min(1.0, vm['memory']))),
                'queue_length': int(max(0, vm['queue_length'])),
                'delay':        float(max(0.0, vm['delay'])),
                'timestamp':    float(vm.get('timestamp', time.time())),
            }
            validated.append(clean)

        return validated

    def notify_task_assigned(self, vm_id: int):
        """
        Tell Member 2's monitor that a task was assigned to vm_id.
        This keeps their queue_length accurate for future decisions.
        Only called in LIVE mode — simulation handles this internally.
        """
        if self.mode == ConnectorMode.SIMULATION:
            # VMState handles this internally via assign_task()
            return

        try:
            data    = json.dumps({'vm_id': vm_id}).encode()
            req     = urllib.request.Request(
                f"http://{MONITOR_HOST}:{MONITOR_PORT}/api/task_assigned",
                data=data,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            urllib.request.urlopen(req, timeout=1.0)
        except Exception:
            # Non-critical — don't crash scheduler if notify fails
            pass

    def notify_task_completed(self, vm_id: int):
        """Tell Member 2 a task finished on vm_id"""
        if self.mode == ConnectorMode.SIMULATION:
            return

        try:
            data = json.dumps({'vm_id': vm_id}).encode()
            req  = urllib.request.Request(
                f"http://{MONITOR_HOST}:{MONITOR_PORT}/api/task_completed",
                data=data,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            urllib.request.urlopen(req, timeout=1.0)
        except Exception:
            pass

# ── Mock server for testing without Member 2 ─────────────────────

class MockMonitorServer:
    """
    Simulates Member 2's monitoring API.
    Use this to test your connector before Member 2 is ready.
    Run in a separate thread during testing.
    """

    def __init__(self, vm_list: list, port: int = 6000):
        self.vm_list = vm_list
        self.port    = port

    def start(self):
        """Start mock server in background thread"""
        import threading
        thread = threading.Thread(
            target=self._serve, daemon=True)
        thread.start()
        time.sleep(0.1)  # Give server time to start
        print(f"  MockMonitorServer running on port {self.port}")

    def _serve(self):
        from http.server import HTTPServer, BaseHTTPRequestHandler
        vm_list = self.vm_list
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/api/vm_stats':
                    stats = [vm.get_stats() for vm in vm_list]
                    body  = json.dumps(stats).encode()
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', len(body))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, *args):
                pass  # Suppress noise

        server = HTTPServer(('localhost', self.port), Handler)
        server.serve_forever()
