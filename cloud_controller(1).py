# Cloud SDN Controller — Ryu Based (Fixed REST API)
# Features:
#   - Multi-tenant isolation (Tenant A: 10.0.1.x, Tenant B: 10.0.2.x)
#   - Firewall rules per tenant
#   - Flow table stats collection
#   - Network bandwidth stats
#   - REST API for dashboard

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ipv4, tcp, udp, ether_types
from ryu.lib import hub
from ryu.app.wsgi import WSGIApplication, ControllerBase, route as wsgi_route
from webob import Response

import json
import time
import logging
import collections

LOG = logging.getLogger('cloud_controller')

TENANT_A_SUBNET = '10.0.1.'
TENANT_B_SUBNET = '10.0.2.'

FIREWALL_RULES = [
    {
        'name'    : 'Block Tenant A -> Tenant B',
        'src_net' : TENANT_A_SUBNET,
        'dst_net' : TENANT_B_SUBNET,
        'proto'   : None,
        'dst_port': None,
        'action'  : 'block'
    },
    {
        'name'    : 'Block Tenant B -> Tenant A',
        'src_net' : TENANT_B_SUBNET,
        'dst_net' : TENANT_A_SUBNET,
        'proto'   : None,
        'dst_port': None,
        'action'  : 'block'
    },
    {
        'name'    : 'Block Telnet (port 23)',
        'src_net' : None,
        'dst_net' : None,
        'proto'   : 'tcp',
        'dst_port': 23,
        'action'  : 'block'
    },
]


class StatsStore:
    def __init__(self):
        self.flow_stats   = {}
        self.port_stats   = {}
        self.switches     = {}
        self.datapaths    = {}   # dpid_str -> datapath object
        self.blocked_pkts = 0
        self.allowed_pkts = 0
        self.blocked_log  = collections.deque(maxlen=50)
        self.last_updated = time.time()

    def to_dict(self):
        # Don't serialize datapath objects
        switches_safe = {
            k: {sk: sv for sk, sv in v.items() if sk != 'datapath'}
            for k, v in self.switches.items()
        }
        return {
            'flow_stats'    : self.flow_stats,
            'port_stats'    : self.port_stats,
            'switches'      : switches_safe,
            'blocked_pkts'  : self.blocked_pkts,
            'allowed_pkts'  : self.allowed_pkts,
            'blocked_log'   : list(self.blocked_log),
            'last_updated'  : self.last_updated,
            'firewall_rules': FIREWALL_RULES,
        }


STORE = StatsStore()


# ── REST API ─────────────────────────────────────────────────
class CloudRestAPI(ControllerBase):

    def __init__(self, req, link, data, **config):
        super(CloudRestAPI, self).__init__(req, link, data, **config)

    @wsgi_route('stats', '/cloud/stats', methods=['GET'])
    def get_stats(self, req, **kwargs):
        host_stats = {}
        try:
            with open('/tmp/cloud_host_stats.json', 'r') as f:
                host_stats = json.load(f)
        except Exception:
            pass

        payload = STORE.to_dict()
        payload['host_stats'] = host_stats
        body = json.dumps(payload, default=str)

        return Response(
            content_type='application/json',
            charset='utf-8',
            headers={'Access-Control-Allow-Origin': '*'},
            body=body.encode('utf-8')
        )

    @wsgi_route('health', '/cloud/health', methods=['GET'])
    def health(self, req, **kwargs):
        body = json.dumps({'status': 'ok', 'time': time.time()})
        return Response(
            content_type='application/json',
            charset='utf-8',
            headers={'Access-Control-Allow-Origin': '*'},
            body=body.encode('utf-8')
        )


# ── Main Controller ───────────────────────────────────────────
class CloudController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {'wsgi': WSGIApplication}

    def __init__(self, *args, **kwargs):
        super(CloudController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        wsgi = kwargs['wsgi']
        wsgi.register(CloudRestAPI, {})
        self.monitor_thread = hub.spawn(self._stats_request_loop)
        LOG.info('Cloud Controller started.')
        LOG.info('REST API -> http://0.0.0.0:8080/cloud/stats')
        LOG.info('Firewall rules: %d loaded', len(FIREWALL_RULES))

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        parser   = datapath.ofproto_parser
        ofproto  = datapath.ofproto
        dpid_str = str(datapath.id)

        # Table-miss entry
        match   = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self._add_flow(datapath, 0, match, actions)

        # Store switch info and datapath ref
        STORE.switches[dpid_str] = {
            'dpid'     : datapath.id,
            'connected': time.strftime('%H:%M:%S'),
            'flows'    : 0,
        }
        STORE.datapaths[dpid_str] = datapath
        LOG.info('Switch %s connected', datapath.id)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg      = ev.msg
        datapath = msg.datapath
        ofproto  = datapath.ofproto
        parser   = datapath.ofproto_parser
        in_port  = msg.match['in_port']

        pkt     = packet.Packet(msg.data)
        eth_pkt = pkt.get_protocol(ethernet.ethernet)
        if eth_pkt is None:
            return
        if eth_pkt.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        dst_mac = eth_pkt.dst
        src_mac = eth_pkt.src
        dpid    = datapath.id

        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][src_mac] = in_port

        # Firewall check
        blocked, rule_name = self._is_blocked(pkt)
        if blocked:
            STORE.blocked_pkts += 1
            ip_pkt = pkt.get_protocol(ipv4.ipv4)
            STORE.blocked_log.append({
                'time'   : time.strftime('%H:%M:%S'),
                'src_mac': src_mac,
                'dst_mac': dst_mac,
                'src_ip' : ip_pkt.src if ip_pkt else '-',
                'dst_ip' : ip_pkt.dst if ip_pkt else '-',
                'rule'   : rule_name,
                'switch' : dpid,
            })
            LOG.warning('[BLOCKED] %s | %s -> %s',
                        rule_name,
                        ip_pkt.src if ip_pkt else src_mac,
                        ip_pkt.dst if ip_pkt else dst_mac)
            return

        STORE.allowed_pkts += 1

        # Forwarding
        out_port = self.mac_to_port[dpid].get(dst_mac, ofproto.OFPP_FLOOD)
        actions  = [parser.OFPActionOutput(out_port)]

        if out_port != ofproto.OFPP_FLOOD:
            ip_pkt = pkt.get_protocol(ipv4.ipv4)
            if ip_pkt:
                match = parser.OFPMatch(
                    in_port=in_port,
                    eth_type=ether_types.ETH_TYPE_IP,
                    ipv4_src=ip_pkt.src,
                    ipv4_dst=ip_pkt.dst
                )
            else:
                match = parser.OFPMatch(
                    in_port=in_port,
                    eth_dst=dst_mac,
                    eth_src=src_mac
                )
            self._add_flow(datapath, 1, match, actions)

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data
        )
        datapath.send_msg(out)

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def flow_stats_reply_handler(self, ev):
        dpid  = str(ev.msg.datapath.id)
        flows = []
        for stat in ev.msg.body:
            flows.append({
                'priority'    : stat.priority,
                'match'       : str(stat.match),
                'packet_count': stat.packet_count,
                'byte_count'  : stat.byte_count,
                'duration_sec': stat.duration_sec,
            })
        STORE.flow_stats[dpid] = flows
        if dpid in STORE.switches:
            STORE.switches[dpid]['flows'] = len(flows)
        STORE.last_updated = time.time()

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def port_stats_reply_handler(self, ev):
        dpid  = str(ev.msg.datapath.id)
        ports = []
        for stat in ev.msg.body:
            ports.append({
                'port_no'   : stat.port_no,
                'rx_packets': stat.rx_packets,
                'tx_packets': stat.tx_packets,
                'rx_bytes'  : stat.rx_bytes,
                'tx_bytes'  : stat.tx_bytes,
                'rx_errors' : stat.rx_errors,
                'tx_errors' : stat.tx_errors,
            })
        STORE.port_stats[dpid] = ports
        STORE.last_updated = time.time()

    def _stats_request_loop(self):
        """Poll every connected switch for flow and port stats every 5s."""
        while True:
            hub.sleep(5)
            for dpid_str, datapath in list(STORE.datapaths.items()):
                try:
                    parser  = datapath.ofproto_parser
                    ofproto = datapath.ofproto
                    # Flow stats
                    datapath.send_msg(parser.OFPFlowStatsRequest(datapath))
                    # Port stats
                    datapath.send_msg(
                        parser.OFPPortStatsRequest(datapath, 0, ofproto.OFPP_ANY))
                except Exception as e:
                    LOG.warning('Stats request failed for %s: %s', dpid_str, e)

    def _is_blocked(self, pkt):
        ip_pkt  = pkt.get_protocol(ipv4.ipv4)
        tcp_pkt = pkt.get_protocol(tcp.tcp)
        udp_pkt = pkt.get_protocol(udp.udp)

        for rule in FIREWALL_RULES:
            if rule['action'] != 'block':
                continue
            if rule.get('src_net'):
                if ip_pkt is None or not ip_pkt.src.startswith(rule['src_net']):
                    continue
            if rule.get('dst_net'):
                if ip_pkt is None or not ip_pkt.dst.startswith(rule['dst_net']):
                    continue
            if rule.get('proto'):
                if rule['proto'] == 'tcp' and tcp_pkt is None:
                    continue
                if rule['proto'] == 'udp' and udp_pkt is None:
                    continue
            if rule.get('dst_port'):
                matched = False
                if tcp_pkt and tcp_pkt.dst_port == rule['dst_port']:
                    matched = True
                if udp_pkt and udp_pkt.dst_port == rule['dst_port']:
                    matched = True
                if not matched:
                    continue
            return True, rule['name']

        return False, None

    def _add_flow(self, datapath, priority, match, actions, idle_timeout=30):
        ofproto = datapath.ofproto
        parser  = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(
            ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=inst,
            idle_timeout=idle_timeout
        )
        datapath.send_msg(mod)
