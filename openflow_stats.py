"""
Member 2 - OpenFlow Network Stats Collector
Plugs into the Ryu controller (Member 1's ryu_app.py).
Member 1 calls update_port_stats() from their Ryu event handler.
"""

import time
import threading


class OpenFlowMonitor:
    """
    Tracks per-link bandwidth utilization using OpenFlow port statistics.
    Member 1 (Ryu controller) calls update_port_stats() every few seconds.
    Member 3 (AVRO) calls get_link_utilization() for routing decisions.
    """

    LINK_CAPACITY_BPS = 10e9   # 10 Gbps — matches the paper's topology

    def __init__(self):
        self._stats      = {}     # {(dpid, port): {rx_bytes, tx_bytes, time}}
        self._bandwidth  = {}     # {(dpid, port): {rx_bw, tx_bw}}
        self._lock       = threading.Lock()
        self.history     = []

    def update_port_stats(self, dpid, port, rx_bytes, tx_bytes):
        """
        Called by Member 1's Ryu handler whenever port stats arrive.
        Computes bandwidth from byte-count deltas.

        Usage in ryu_app.py:
            from openflow_stats import OpenFlowMonitor
            of_monitor = OpenFlowMonitor()

            @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
            def port_stats_reply_handler(self, ev):
                for stat in ev.msg.body:
                    of_monitor.update_port_stats(
                        ev.msg.datapath.id,
                        stat.port_no,
                        stat.rx_bytes,
                        stat.tx_bytes
                    )
        """
        key = (dpid, port)
        now = time.time()

        with self._lock:
            if key in self._stats:
                prev  = self._stats[key]
                dt    = now - prev['time']
                if dt > 0:
                    rx_bw = (rx_bytes - prev['rx_bytes']) / dt
                    tx_bw = (tx_bytes - prev['tx_bytes']) / dt
                    self._bandwidth[key] = {
                        'rx_bw': max(0, rx_bw),
                        'tx_bw': max(0, tx_bw),
                        'utilization': max(0, tx_bw) / self.LINK_CAPACITY_BPS
                    }

            self._stats[key] = {
                'rx_bytes': rx_bytes,
                'tx_bytes': tx_bytes,
                'time':     now
            }

        self._log_snapshot()

    def get_link_utilization(self):
        """
        Returns utilization ratio (0.0–1.0) per (dpid, port).
        Called by AVRO scheduler when making routing decisions.
        """
        with self._lock:
            return {
                key: bw['utilization']
                for key, bw in self._bandwidth.items()
            }

    def get_congested_links(self, threshold=0.7):
        """Returns list of links with utilization above threshold."""
        return [
            key for key, util in self.get_link_utilization().items()
            if util > threshold
        ]

    def get_summary(self):
        """Human-readable summary of all link stats."""
        utils = self.get_link_utilization()
        if not utils:
            return "No link stats collected yet."
        lines = [f"{'Switch':<10} {'Port':<6} {'Utilization':>12}"]
        lines.append("-" * 32)
        for (dpid, port), util in sorted(utils.items()):
            bar = "█" * int(util * 20)
            lines.append(f"SW {dpid:<7} {port:<6} {util*100:>6.1f}%  {bar}")
        return "\n".join(lines)

    def _log_snapshot(self):
        self.history.append({
            'time':       time.time(),
            'bandwidth':  dict(self._bandwidth)
        })
        # Keep only last 1000 snapshots to save memory
        if len(self.history) > 1000:
            self.history.pop(0)
