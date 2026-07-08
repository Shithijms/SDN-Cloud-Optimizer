from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ipv4, tcp, udp, arp, ether_types
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
VIRTUAL_SERVICE_IP = '10.0.100.100'

FIREWALL_RULES = [
    {'name': 'Block Tenant A -> Tenant B', 'src_net': TENANT_A_SUBNET, 'dst_net': TENANT_B_SUBNET, 'proto': None, 'dst_port': None, 'action': 'block'},
    {'name': 'Block Tenant B -> Tenant A', 'src_net': TENANT_B_SUBNET, 'dst_net': TENANT_A_SUBNET, 'proto': None, 'dst_port': None, 'action': 'block'},
    {'name': 'Block Telnet (port 23)', 'src_net': None, 'dst_net': None, 'proto': 'tcp', 'dst_port': 23, 'action': 'block'},
]

class StatsStore:
    def __init__(self):
        self.flow_stats = {}
        self.port_stats = {}
        self.switches = {}
        self.datapaths = {}
        self.blocked_pkts = 0
        self.allowed_pkts = 0
        self.blocked_log = collections.deque(maxlen=50)
        self.last_updated = time.time()
        self.mac_to_port = {}

    def to_dict(self):
        switches_safe = {
            str(k): {sk: sv for sk, sv in v.items() if sk != 'datapath'}
            for k, v in self.switches.items()
        }
        return {
            'flow_stats': self.flow_stats,
            'port_stats': self.port_stats,
            'switches': switches_safe,
            'blocked_pkts': self.blocked_pkts,
            'allowed_pkts': self.allowed_pkts,
            'blocked_log': list(self.blocked_log),
            'last_updated': self.last_updated,
            'firewall_rules': FIREWALL_RULES,
        }

STORE = StatsStore()

class CloudRestAPI(ControllerBase):
    def __init__(self, req, link, data, **config):
        super(CloudRestAPI, self).__init__(req, link, data, **config)
        self.controller = data['controller']

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
        body = json.dumps(payload, default=str).encode('utf-8')
        return Response(content_type='application/json', charset='utf-8',
                        headers={'Access-Control-Allow-Origin': '*'}, body=body)

    @wsgi_route('health', '/cloud/health', methods=['GET'])
    def health(self, req, **kwargs):
        return Response(content_type='application/json', body=b'{"status":"ok"}')

    @wsgi_route('assign', '/cloud/assign', methods=['POST'])
    def install_scheduled_flow(self, req, **kwargs):
        try:
            body = req.json_body
        except Exception:
            return Response(status=400, body="Invalid JSON")

        required = ['src_ip', 'dst_ip', 'dst_port', 'protocol', 'target_vm_ip']
        if not all(k in body for k in required):
            return Response(status=400, body="Missing fields")

        src_ip = body['src_ip']
        virt_ip = body['dst_ip']
        dst_port = body['dst_port']
        proto = body['protocol']
        target_ip = body['target_vm_ip']

        target_mac = None
        out_port = None
        dpid = None

        try:
            with open('/tmp/cloud_host_stats.json', 'r') as f:
                stats = json.load(f)
            for host, data in stats.items():
                if host.startswith('h') and data.get('ip') == target_ip:
                    idx = int(host[1:])
                    target_mac = f"00:00:00:00:00:{idx:02x}"
                    for dpid_str, table in STORE.mac_to_port.items():
                        if target_mac in table:
                            out_port = table[target_mac]
                            dpid = int(dpid_str)
                            break
                    break
        except Exception:
            pass

        if not target_mac or out_port is None:
            return Response(status=404, body="Cannot determine output port for target VM")

        datapath = STORE.datapaths.get(str(dpid))
        if not datapath:
            return Response(status=404, body="Datapath not active")

        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        if proto == 'tcp':
            match = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP,
                                    ipv4_src=src_ip, ipv4_dst=virt_ip,
                                    ip_proto=6, tcp_dst=dst_port)
        elif proto == 'udp':
            match = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP,
                                    ipv4_src=src_ip, ipv4_dst=virt_ip,
                                    ip_proto=17, udp_dst=dst_port)
        else:
            return Response(status=400, body="Unsupported protocol")

        actions = [parser.OFPActionSetField(ipv4_dst=target_ip),
                   parser.OFPActionOutput(out_port)]
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=100, match=match,
                                instructions=inst, idle_timeout=30, hard_timeout=0)
        datapath.send_msg(mod)
        return Response(status=200, body="Flow installed")


class CloudController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {'wsgi': WSGIApplication}

    def __init__(self, *args, **kwargs):
        super(CloudController, self).__init__(*args, **kwargs)
        wsgi = kwargs['wsgi']
        wsgi.register(CloudRestAPI, {'controller': self})
        self.monitor_thread = hub.spawn(self._stats_request_loop)
        LOG.info('Cloud Controller started')

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=0, match=match,
                                instructions=inst, idle_timeout=0, hard_timeout=0)
        datapath.send_msg(mod)
        dpid_str = str(datapath.id)
        STORE.datapaths[dpid_str] = datapath
        STORE.switches[dpid_str] = {'dpid': datapath.id, 'connected': time.strftime('%H:%M:%S'), 'flows': 0}
        LOG.info('Switch %s connected', datapath.id)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth is None:
            return
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        dpid = datapath.id
        STORE.mac_to_port.setdefault(dpid, {})
        STORE.mac_to_port[dpid][eth.src] = in_port

        arp_pkt = pkt.get_protocol(arp.arp)
        if arp_pkt and arp_pkt.opcode == arp.ARP_REQUEST and arp_pkt.dst_ip == VIRTUAL_SERVICE_IP:
            src_mac = '02:00:00:00:00:01'
            arp_reply = packet.Packet()
            arp_reply.add_protocol(ethernet.ethernet(ethertype=ether_types.ETH_TYPE_ARP,
                                                     dst=arp_pkt.src_mac, src=src_mac))
            arp_reply.add_protocol(arp.arp(opcode=arp.ARP_REPLY, src_mac=src_mac,
                                           src_ip=arp_pkt.dst_ip, dst_mac=arp_pkt.src_mac,
                                           dst_ip=arp_pkt.src_ip))
            actions = [parser.OFPActionOutput(in_port)]
            out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                      in_port=in_port, actions=actions, data=arp_reply.data)
            datapath.send_msg(out)
            return

        blocked, rule_name = self._is_blocked(pkt)
        if blocked:
            STORE.blocked_pkts += 1
            ip_pkt = pkt.get_protocol(ipv4.ipv4)
            STORE.blocked_log.append({
                'time': time.strftime('%H:%M:%S'),
                'src_mac': eth.src, 'dst_mac': eth.dst,
                'src_ip': ip_pkt.src if ip_pkt else '-',
                'dst_ip': ip_pkt.dst if ip_pkt else '-',
                'rule': rule_name, 'switch': dpid,
            })
            LOG.warning('[BLOCKED] %s', rule_name)
            return

        STORE.allowed_pkts += 1
        out_port = STORE.mac_to_port[dpid].get(eth.dst, ofproto.OFPP_FLOOD)
        actions = [parser.OFPActionOutput(out_port)]

        if out_port != ofproto.OFPP_FLOOD:
            ip_pkt = pkt.get_protocol(ipv4.ipv4)
            if ip_pkt:
                match = parser.OFPMatch(in_port=in_port, eth_type=ether_types.ETH_TYPE_IP,
                                        ipv4_src=ip_pkt.src, ipv4_dst=ip_pkt.dst)
            else:
                match = parser.OFPMatch(in_port=in_port, eth_dst=eth.dst, eth_src=eth.src)
            self._add_flow(datapath, 1, match, actions)

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data
        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                   in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def flow_stats_reply_handler(self, ev):
        dpid = str(ev.msg.datapath.id)
        flows = []
        for stat in ev.msg.body:
            flows.append({'priority': stat.priority, 'match': str(stat.match),
                          'packet_count': stat.packet_count, 'byte_count': stat.byte_count,
                          'duration_sec': stat.duration_sec})
        STORE.flow_stats[dpid] = flows
        if dpid in STORE.switches:
            STORE.switches[dpid]['flows'] = len(flows)
        STORE.last_updated = time.time()

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def port_stats_reply_handler(self, ev):
        dpid = str(ev.msg.datapath.id)
        ports = []
        for stat in ev.msg.body:
            ports.append({'port_no': stat.port_no, 'rx_packets': stat.rx_packets,
                          'tx_packets': stat.tx_packets, 'rx_bytes': stat.rx_bytes,
                          'tx_bytes': stat.tx_bytes, 'rx_errors': stat.rx_errors,
                          'tx_errors': stat.tx_errors})
        STORE.port_stats[dpid] = ports
        STORE.last_updated = time.time()

    def _stats_request_loop(self):
        while True:
            hub.sleep(5)
            for dpid_str, datapath in list(STORE.datapaths.items()):
                try:
                    parser = datapath.ofproto_parser
                    datapath.send_msg(parser.OFPFlowStatsRequest(datapath))
                    datapath.send_msg(parser.OFPPortStatsRequest(datapath, 0, datapath.ofproto.OFPP_ANY))
                except Exception as e:
                    LOG.warning('Stats request failed for %s: %s', dpid_str, e)

    def _is_blocked(self, pkt):
        ip_pkt = pkt.get_protocol(ipv4.ipv4)
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
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=priority, match=match,
                                instructions=inst, idle_timeout=idle_timeout, hard_timeout=0)
        datapath.send_msg(mod)

