from ats import tcl
from ats import aetest
import logging
from ats.log.utils import banner
from ats.topology import loader
from hltapi.legacy import Ixia
from ats.tcl import tclstr
import re
from IPython import embed
import sys
import pdb
import time
import pprint
import itertools
import copy
import random
import importlib
from ats.easypy import runtime
# IMPORT THE JOBFILE INTO NAMESPACE
jobfile = runtime.job.name  # GET JOB FILE NAME
a = importlib.import_module(jobfile)  # IMPORT THE JOB FILE INTO NAMESPACE
SrScriptArgs = a.SrScriptArgs()  # INSTANCE OF SRSCRIPTARGS
tcl.q.source('/auto/sjgate/autotest/regression/viking/gate/scripts/libInit')
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
log.info("""
TOPOLOGY :
   +----------------------------------------------------------+
   |                                                          |
   |                                                          |
+------+      +------+       +------+       +------+       +------+
|      |      |      |       |      |       |      |       |      |
|  R1  |------|  R2  |------ |  R3  |------ |  R4  |------ |  R5  |
|      |      |      |       |      |       |      |       |      |
+------+      +------+       +------+       +------+       +------+
   |                                           |               |
   |                                           |               |
   |                                           |               |
+------+                                    +------+        +------+
|      |                                    |      |        |      |
| ixia |                                    | ixia |        | ixia |
|      |                                    |      |        |      |
+------+                                    +------+        +------+
""")
class ForkedPdb(pdb.Pdb):
    '''A Pdb subclass that may be used
    from a forked multiprocessing child
    '''
    def interaction(self, *args, **kwargs):
        _stdin = sys.stdin
        try:
            sys.stdin = open('/dev/stdin')
            pdb.Pdb.interaction(self, *args, **kwargs)
        finally:
            sys.stdin = _stdin
def get_rtr_intfs(num_intfs, rtr_intf_alias, rtr, msg):
    """
    Will return a string list of router interfaces so tcl Procs
    can process the interface data
    """
    # getting number of interfaces
    rtr_num_intfs = num_intfs
    # getting interface alias name
    rtr_intf_alias = rtr_intf_alias
    index = 0
    count = 1
    rtr_str_list = []
    log.info('@@@ LINKS FOR {} @@@'.format(msg))
    while count <= rtr_num_intfs:
        # convert count int to str
        count_str = str(count)
        # remove last digit of alias rtr6_rtr4_intf.1
        intf_sub = re.sub(r'\d+$', count_str, rtr_intf_alias)
        rtr_intf_list = rtr.interfaces['{}'.format(intf_sub)]
        rtr_str = str(rtr_intf_list)
        #match typhoon or tomahawk interfaces
        mo = re.search(r'(?:\w+/\d/\d+/\d+/\d+|\w+/\d+/\d+/\d+)', rtr_str)
        rtr_str_list.append(mo.group(0))
        log.info("{} selected {}".format(rtr, rtr_str_list[index]))
        count += 1
        index += 1
    return rtr_str_list
def get_ixia_handles(tgen_intf_list,port_list_flag=0):
    '''return a list of ixia handles. converts the following
       line : Interface 2/2 at 0xf686d3ec and return just the
       ixia port handle. the port_list_flag when enabled will
       return a list as such ['1/2/2', '1/7/1', '1/7/5'] when
       not enabled the return list will be as ['2/2', '7/1', '7/5']'''
    tgen_handle_list = []
    port_handle_list = []
    for intf in tgen_intf_list:
        mo = re.search(r'Interface (\d+\/\d+)', str(intf))
        tgen_handle_list.append(mo.group(1))
        port_handle_list.append('1/{}'.format(mo.group(1)))
    if port_list_flag == 0:
        return tgen_handle_list
    if port_list_flag == 1:
        return port_handle_list
def config_sr_tunnels(tun_dst, tunnel_id, exp_list_names=None,
                      exp_ip_list=None, num_dynamic_tuns=0):
    '''This function is used to configure segment routing tunnels.
       this function extends the existing tcl proc ::xr::config::te_tunnel
       and allows you to configure both dynamic path and explicit path
       in a single function all.'''
    place_holder_cfg = ''
    for num in range(num_dynamic_tuns):
        ###############################
        # CONFIG DYNAMIC SR TUNNELS
        ###############################
        returnList = tcl.q.eval('::xr::config::te_tunnel '
                                '-tunnel_dst_ip {} '
                                '-tunnel_dst_mask 255.255.255.255 '
                                '-autoroute_announce '
                                '-path_option_type  dynamic '
                                '-num_of_tunnels 1 '
                                '-segment_routing_path_option 1 '
                                '-tunnel_unnumbered_intf loopback0 '
                                '-tunnel_id {} '.format(tun_dst, tunnel_id))
        place_holder_cfg += returnList.config_str
        tunnel_id += 1
    if exp_list_names is not None and exp_ip_list is not None:
        for p_names, path_ip in itertools.zip_longest(exp_list_names,
                                                      exp_ip_list):
            ###############################
            # CONFIG EXPLICIT SR TUNNELS
            ###############################
            returnList = tcl.q.eval('::xr::config::te_tunnel '
                                    '-tunnel_dst_ip {} '
                                    '-tunnel_unnumbered_intf loopback0 '
                                    '-tunnel_dst_mask 255.255.255.255 '
                                    '-autoroute_announce '
                                    '-explicit_path_ip {} '
                                    '-num_of_tunnels 1 '
                                    '-explicit_path_name path-{}-intf-tunnel-id '
                                    '-segment_routing_path_option 1 '
                                    '-tunnel_id {} '.format(tun_dst,
                                                            tclstr(path_ip),
                                                            tclstr(p_names),
                                                            tunnel_id,))
            place_holder_cfg += returnList.config_str
            tunnel_id += 1
    return place_holder_cfg
def make_sub_list(l, n):
    '''This function is used to slice one list into sub list'''
    n = max(1, n)
    return [l[i:i + n] for i in range(0, len(l), n)]
def ip_add_convert(list_of_list, ip_digit='1'):
    '''This function is used to change the last value of an ip address
       in a list of sub-list.'''
    new_list = []
    for item in list_of_list:
        for element in item:
            if '192.168' in element:
                continue
            else:
                mo = re.sub(r'\d+$', ip_digit , element)
                new_list.append(mo)
    return new_list
def autoroute_announce(rtr, no_aa_tunnel_list, aa_tunnel_list):
    '''This will be used to remove autoroute announce for one
       set of tunnels and also add autoroute announce back to
       another set of tunnels.'''
    for uncfg_aa_tun in no_aa_tunnel_list:
        # removing autoroute announce
        rtr.configure('''interface {}
                      no autoroute announce'''.format(uncfg_aa_tun))
    for aa_tun in aa_tunnel_list:
        # Adding autoroute announce back to single tunnel
        rtr.configure('''interface {}
                      autoroute announce'''.format(aa_tun))
def packet_tolerance(pkts_tx_ixia=500000, tolerance_percent=.05):
    '''Will calculate a packet tolorence. For example if 100 packets are
       transmited via ixia and the tolorence percent is set at .05 then the
       tolorence value would be set at 95 packets'''
    pkt_tol = tolerance_percent * pkts_tx_ixia
    total_pkt_tol = pkts_tx_ixia - pkt_tol
    return total_pkt_tol
class Debug(object):
    '''Used when test cases fail. Will call the relevent show commands
       to help debug the feature.'''
    def router(rtr, lc, nbr_ip_list):
        """Collect debug info."""
        log.info(banner('COLLECTING DEBUG INFORMATON...'))
        # configs
        print(rtr.execute('show run'))
        # forwarding
        print(rtr.execute('show drops'))
        print(rtr.execute('show controller np counters all'))
        print(rtr.execute('show mpls forwarding tunnels detail'))
        print(rtr.execute('show mpls traffic-eng tunnels detail'))
        print(rtr.execute('show l2vpn bridge-domain detail'))
        print(rtr.execute('show l2vpn forwarding bridge-domain mac-address hardware egress loc {}'.format(lc)))
        for nbr in nbr_ip_list:
            log.info('### OUTPUT FOR {} ADDRESS'.format(nbr))
            print(rtr.execute('show route {} detail'.format(nbr)))
            print(rtr.execute('show cef {} hardware egress detail location {}'.format(nbr, lc)))
class Clear(object):
    '''Used for clearing counters on router'''
    def counters(rtr_list):
        for rtr in rtr_list:
            log.info('clearing counters on {}'.format(rtr))
            rtr.execute('clear counters all')
            rtr.execute('clear controller np counters all')
            rtr.execute('clear mpls forwarding counters')
            rtr.execute('clear l2vpn counters l2fwd')
class Verify(object):
    """Class used to verify various protocols."""
    def routing_protocol(rtr, expected_neighbors, protocol='isis',
                         poll_interval=30):
        '''verification method for checking the expected number of
        isis adjacency or ospf neighbors'''
        if protocol == 'isis':
            log.info('routing protocol selected is {}'.format(protocol))
            show_cmd = 'show isis adjacency'
        elif protocol == 'ospf':
            log.info('routing protocol selected is {}'.format(protocol))
            show_cmd = 'show ospf neighbor'
        else:
            log.info('''unknown routing protocol selected please either select
                  isis or ospf''')
        attempts = 1
        result = 0
        while attempts <= 5:
            log.info('attemt = {} on {}'.format(attempts, rtr))
            show_cmd_output = rtr.execute(show_cmd)
            if 'Total adjacency count: {}'.format(expected_neighbors) in show_cmd_output:
                log.info('''pass expected {} isis adjacency on {}'''.format(
                                                            expected_neighbors,
                                                            rtr))
                break
            if 'Total neighbor count: {}'.format(expected_neighbors) in show_cmd_output:
                log.info('''pass expected {} ospf neighbor on {}'''.format(
                                                            expected_neighbors,
                                                            rtr))
                break
            if attempts == 5 and protocol == 'isis':
                log.error('''failed to find the expected number of isis adjacency
                         expected {}'''.format(expected_neighbors))
                result = 1
            if attempts == 5 and protocol == 'ospf':
                log.error('''failed to find the expected number of ospf neighbors
                         expected {}'''.format(expected_neighbors))
                result = 1
            time.sleep(poll_interval)
            attempts += 1
        return result
    def l2vpn(rtr, l2vpn_nbr_ip_list, pw_id='1', poll_interval=15):
        result = 0
        attempts = 1
        expected_show_result = 'pw-id {}, state: up'.format(pw_id)
        for ip in l2vpn_nbr_ip_list:
            show_cmd = 'show l2vpn bridge-domain neighbor {}'.format(ip)
            while attempts <= 5:
                show_cmd_output = rtr.execute(show_cmd)
                print(show_cmd_output)
                if expected_show_result in show_cmd_output:
                    log.info('pass l2vpn up nbr {} on {}'.format(ip, rtr))
                    break
                if attempts == 5:
                    log.error('''fail could not verify nbr {} is up
                             on {}'''.format(ip, rtr))
                    result = 1
                attempts += 1
                time.sleep(poll_interval)
        return result
    def te_tunnels(rtr, all_flag=1, tun_list=[]):
        result = 0
        log.info(banner('VERIFY TE-TUNNELS ON {}'.format(rtr)))
        i = 1
        # verify group of tunnels
        if all_flag == 1:
            while i <= 5:
                output = rtr.execute('show interface tunnel-te* brief')
                if i == 5 and 'down' in output:
                    result = 1
                    log.error('not all tunnels came up')
                elif 'down' in output:
                    print('tunnels are polling...')
                else:
                    log.info('pass all tunnels are up')
                    break
                i += 1
                time.sleep(20)
        else:
            # verify single tunnel via list
            for tun in tun_list:
                output = rtr.execute('show interface {} brief'.format(tun))
                while i <= 5:
                    if i == 5 and 'down' in output:
                        result = 1
                        log.error('not all tunnels came up')
                    elif 'up          up' in output:
                        log.info('pass tunnel is up')
                        break
                    else:
                        log.info('polling...')
                        time.sleep(20)
                    i += 1
        return result
    def ixia_traffic_rx(ixia_result=0, packet_tolerance=5.000, wait_time=60):
        # getting common setup instance attributes
        sr = common_setup(wait_time)
        # RUN IXIA TRAFFIC
        sr.ixia.traffic_control(action='run', port_handle=sr.port_handle_list)
        time.sleep(wait_time)
        # verify unicast traffic streams
        for streams_ids in stream_list[0:2]:
            traffic_status = sr.ixia.traffic_stats(mode='stream ',
                                                streams='{} '.format(streams_ids))
            tx_pkts = traffic_status[sr.port_handle_list[0]].stream[streams_ids].tx.total_pkts
            exp_pkts = traffic_status[sr.port_handle_list[0]].stream[streams_ids].rx.expected_pkts
            pkt_loss = traffic_status[sr.port_handle_list[0]].stream[streams_ids].rx.loss_percent
            if float(pkt_loss) >= packet_tolerance:
                log.info('''fail stream {} tx_pkts {} exp_pkts {} pkt loss percent {}'''
                     .format(streams_ids, tx_pkts, exp_pkts, pkt_loss))
                ixia_result = 1
            else:
                log.info('''pass stream {} tx_pkts {} exp_pkts {} pkt loss percent {}'''
                     .format(streams_ids, tx_pkts, exp_pkts, pkt_loss))
        # verify mcast traffic streams
        for streams_ids in stream_list[2:5]:
            traffic_status = sr.ixia.traffic_stats(mode='stream ',
                                                streams='{} '.format(streams_ids))
            tx_pkts = traffic_status[sr.port_handle_list[0]].stream[streams_ids].tx.total_pkts
            exp_pkts_p1 = traffic_status[sr.port_handle_list[1]].stream[streams_ids].rx.expected_pkts
            exp_pkts_p2 = traffic_status[sr.port_handle_list[2]].stream[streams_ids].rx.expected_pkts
            pkt_loss_p1 = traffic_status[sr.port_handle_list[1]].stream[streams_ids].rx.loss_percent
            pkt_loss_p2 = traffic_status[sr.port_handle_list[2]].stream[streams_ids].rx.loss_percent
            if float(pkt_loss_p1) and float(pkt_loss_p2) >= packet_tolerance:
                print('''fail for stream id {} tx pkts sent on {} = {} rx pkts on
                        {} = {} loss percent {} rx pkts on {} = {} loss percent {}
                        '''.format(streams_ids, sr.port_handle_list[0], tx_pkts,
                                   sr.port_handle_list[1], exp_pkts_p1,
                                   pkt_loss_p1, sr.port_handle_list[2],
                                   exp_pkts_p2, pkt_loss_p2))
                ixia_result = 1
            else:
                print('''pass for stream id {} tx pkts sent on {} = {} rx pkts on
                        {} = {} loss percent {} rx pkts on {} = {} loss percent {}
                        '''.format(streams_ids, sr.port_handle_list[0], tx_pkts,
                                   sr.port_handle_list[1], exp_pkts_p1,
                                   pkt_loss_p1, sr.port_handle_list[2],
                                   exp_pkts_p2, pkt_loss_p2))
        return ixia_result
    def route(rtr, ip_dst_list, tunnel_lst, result=0):
        '''Verify route going over tunnel'''
        i = 0
        for route in ip_dst_list:
            output = rtr.execute('show route {}'.format(route))
            print(output)
            if '{}, via {}'.format(route, tunnel_lst[i]) in output:
                log.info('pass expected {} via {}'.format(route, tunnel_lst[i]))
            else:
                log.warning('fail expected {} via {}'.format(route, tunnel_lst[i]))
                result = 1
            i += 1
        return result
    def interface_counters(rtr, tunnel_list, tolerance_percent=.05,
                           pkts_tx=400000, result=0):
        '''Verify interface counters on router'''
        pkt_tol = tolerance_percent * pkts_tx
        total_pkt_tol = pkts_tx - pkt_tol
        tcl.q.eval('package require router_show')
        for tun in tunnel_list:
            log.info(banner('intf traffic stats for  {}'.format(tun)))
            # getting tunnel id
            tun_id = re.search(r'(\d+)', tun)
            tun_id_tt = 'tt' + tun_id.group(0)
            # getting tunnel packet accounting
            klist = tcl.q.eval('router_show -device {} '
                               '-cmd show interface {} accounting '
                               '-os_type xr '.format(rtr, tun))
            pkts = klist.totals.pkts_out
            # verify packet accounting over tunnel
            if int(pkts) >= total_pkt_tol:
                print('''pass pkts out {} is {} expected {} tolerance {}
                      '''.format(tun, pkts, pkts_tx, total_pkt_tol))
            else:
                print('''fail pkts out {} is {} expected {} tolerance {}
                      '''.format(tun, pkts, pkts_tx, total_pkt_tol))
                result = 1
            # getting mpls fwd stats for tunnel
            klist = tcl.q.eval('router_show -device {} '
                               '-cmd show mpls forwarding tunnels {} detail '
                               '-os_type xr '.format(rtr, tclstr(tun_id.group(0))))
            mpls_fwd_pkts = klist.tunid[tun_id_tt].pkts
            if int(mpls_fwd_pkts) >= total_pkt_tol:
                log.info('''pass mpls fwd pkts out {} is {} expected {}
                          tolerance {}'''.format(tun, pkts, pkts_tx,
                                                 total_pkt_tol))
            else:
                log.info('''fail mpls fwd pkts out {} is {} expected {}
                         tolerance'''.format(tun, pkts, pkts_tx,
                                             total_pkt_tol))
                result = 1
            # getting tunnel fwd interface
            klist = tcl.q.eval('router_show -device {} '
                               '-cmd show mpls forwarding tunnels {} '
                               '-os_type xr '.format(rtr, tclstr(tun_id.group(0))))
            tun_out_intf = klist.tunid[tun_id_tt].prefix
            #tun_out_intf = klist.tunid[tun_id_tt].intf <---fix proc
            # tcl proc uses dots to bars so sub int will have a _ instead of a .
            # this will need to be replaced using regsub
            if '_' in tun_out_intf:
                tun_out_intf = re.sub(r'_', '.', tun_out_intf)
            log.info('''tunnel {} egress interface is {}
                     '''.format(tun, tun_out_intf))
            # verify traffic over tunnel physical interface
            klist = tcl.q.eval('router_show -device {} '
                               '-cmd show interface {} accounting '
                               '-os_type xr '.format(rtr, tun_out_intf))
            physical_intf_pkts = klist.totals.pkts_out
            if int(physical_intf_pkts) >= total_pkt_tol:
                log.info('''pass pkts out {} is {} tolerance {}
                '''.format(tun_out_intf, physical_intf_pkts, total_pkt_tol))
            else:
                log.warning('''fail pkts out {} is {} tolerance {}
                            '''.format(tun_out_intf, physical_intf_pkts))
        return result
###################################################################
###                  COMMON SETUP SECTION                       ###
###################################################################
class common_setup(aetest.CommonSetup):
    '''common setup for SR-TE with VPLS'''
    # load yaml file
    testbed = loader.load(SrScriptArgs.testbed_file)
    # Grab the device object of the uut device with that name
    r1 = testbed.devices[SrScriptArgs.uut_list[0]]
    r2 = testbed.devices[SrScriptArgs.uut_list[1]]
    r3 = testbed.devices[SrScriptArgs.uut_list[2]]
    r4 = testbed.devices[SrScriptArgs.uut_list[3]]
    r5 = testbed.devices[SrScriptArgs.uut_list[4]]
    uut_list = [r1, r2, r3, r4, r5]
    # get ixia interfaces from yaml file
    tgen_r1_intf = testbed.devices.ixia.\
        interfaces[SrScriptArgs.tgen1_r1_intfs_alias]
    tgen_r4_intf = testbed.devices.ixia.\
        interfaces[SrScriptArgs.tgen1_r4_intfs_alias]
    tgen_r5_intf = testbed.devices.ixia.\
        interfaces[SrScriptArgs.tgen1_r5_intfs_alias]
    tgen_intf_list = [tgen_r1_intf, tgen_r4_intf, tgen_r5_intf]
    # get interface list for r1 to t2
    r1_r2_intfs = get_rtr_intfs(SrScriptArgs.r1_r2_num_intfs,
                                SrScriptArgs.r1_r2_intfs_alias,
                                r1, 'R1 to R2')
    # get frr interface links r1 to r5
    r1_r5_intfs = get_rtr_intfs(SrScriptArgs.r1_r5_num_intfs,
                                SrScriptArgs.r1_r5_intfs_alias,
                                r1, 'R1 to R5')
    # getting interfaces to tgen1 to rtr1
    r1_tgen_intfs = get_rtr_intfs(SrScriptArgs.r1_tgen1_num_intfs,
                                  SrScriptArgs.r1_tgen1_intfs_alias,
                                  r1, 'R1 to TGEN')
    # get interface list for r2 to t1
    r2_r1_intfs = get_rtr_intfs(SrScriptArgs.r2_r1_num_intfs,
                                SrScriptArgs.r2_r1_intfs_alias,
                                r2, 'R2 to R1')
    # get interface list for r2 to t3
    r2_r3_intfs = get_rtr_intfs(SrScriptArgs.r2_r3_num_intfs,
                                SrScriptArgs.r2_r3_intfs_alias,
                                r2, 'R2 to R3')
    # get interface list for r3 to r2
    r3_r2_intfs = get_rtr_intfs(SrScriptArgs.r3_r2_num_intfs,
                                SrScriptArgs.r3_r2_intfs_alias,
                                r3, 'R3 to R2')
    # get interface list for r3 to t4
    r3_r4_intfs = get_rtr_intfs(SrScriptArgs.r3_r4_num_intfs,
                                SrScriptArgs.r3_r4_intfs_alias,
                                r3, 'R3 to R4')
    # get interface list for r4 to r3
    r4_r3_intfs = get_rtr_intfs(SrScriptArgs.r4_r3_num_intfs,
                                SrScriptArgs.r4_r3_intfs_alias,
                                r4, 'R4 to R3')
    # get interface list for r4 to r5
    r4_r5_intfs = get_rtr_intfs(SrScriptArgs.r4_r5_num_intfs,
                                SrScriptArgs.r4_r5_intfs_alias,
                                r4, 'R4 to R5')
    # getting interfaces to R4 to TGEN
    r4_tgen_intfs = get_rtr_intfs(SrScriptArgs.r4_tgen1_num_intfs,
                                  SrScriptArgs.r4_tgen1_intfs_alias,
                                  r4, 'R4 to TGEN')
    # get interface list for r5 to r4
    r5_r4_intfs = get_rtr_intfs(SrScriptArgs.r5_r4_num_intfs,
                                SrScriptArgs.r5_r4_intfs_alias,
                                r5, 'R5 to R4')
    # get frr interface links r5 to r1
    r5_r1_intfs = get_rtr_intfs(SrScriptArgs.r5_r1_num_intfs,
                                SrScriptArgs.r5_r1_intfs_alias,
                                r5, 'R5 to R1')
    # getting interfaces to tgen1 to rtr5
    r5_tgen_intfs = get_rtr_intfs(SrScriptArgs.r5_tgen1_num_intfs,
                                  SrScriptArgs.r5_tgen1_intfs_alias,
                                  r5, 'R5 to TGEN')
    # getting list of ixia port handles
    tgen_handle_list = get_ixia_handles(tgen_intf_list)
    port_handle_list = get_ixia_handles(tgen_intf_list, port_list_flag=1)
    tgen_port_handle1 = port_handle_list[0]
    tgen_port_handle2 = port_handle_list[1]
    tgen_port_handle3 = port_handle_list[2]
    rtr1_config_str = ''
    rtr2_config_str = ''
    rtr3_config_str = ''
    rtr4_config_str = ''
    rtr5_config_str = ''
    rtr1_tgen1_cfg_intfs = []
    rtr4_tgen1_cfg_intfs = []
    rtr5_tgen1_cfg_intfs = []
    rtr1_rtr2_cfg_intf_list = []
    rtr2_rtr1_cfg_intf_list = []
    rtr2_rtr3_cfg_intf_list = []
    rtr3_rtr2_cfg_intf_list = []
    rtr3_rtr4_cfg_intf_list = []
    rtr4_rtr3_cfg_intf_list = []
    rtr4_rtr5_cfg_intf_list = []
    rtr5_rtr4_cfg_intf_list = []
    rtr1_rtr5_cfg_intf_list = []
    rtr5_rtr1_cfg_intf_list = []
    r1_lo = '192.168.1.1'
    r2_lo = '192.168.2.1'
    r3_lo = '192.168.3.1'
    r4_lo = '192.168.4.1'
    r5_lo = '192.168.5.1'
    global proto
    proto = SrScriptArgs.routing_proto
    global dynamic_tun_num
    # selecting random number for tunnel
    dynamic_tun_num = random.randint(0, 1)
    # selecting random tunnel
    global random_tun_num
    random_tun_num = random.randint(0, 5)
    # R1 to R5 explicit path list to R5 primary path
    r1_r5_exp_path1_lo0 = [r2_lo, r3_lo, r4_lo, r5_lo]
    r5_r1_exp_path1_lo0 = [r4_lo, r3_lo, r2_lo, r1_lo]
    r1_r5_exp_path2_main = ['12.1.1.2', '23.1.1.2', '34.1.1.2', '45.1.1.2']
    r1_r5_exp_path3_sub = ['12.1.2.2', '23.1.1.2', '34.1.1.2', '45.1.1.2']
    r1_r5_exp_path4_be = ['12.1.3.2', '23.1.1.2', '34.1.1.2', '45.1.1.2']
    r1_r5_exp_path_list = [r1_r5_exp_path1_lo0, r1_r5_exp_path2_main,
                           r1_r5_exp_path3_sub, r1_r5_exp_path4_be]
    # R5 to R1 explist path list
    r5_list = copy.deepcopy(r1_r5_exp_path_list)
    r5_r1_exp_path_list = ip_add_convert(r5_list, ip_digit='1')
    r5_r1_exp_path_list = make_sub_list(r5_r1_exp_path_list, 4)
    for item in r5_r1_exp_path_list:
        item.reverse()
    r5_r1_exp_path_list.insert(0, r5_r1_exp_path1_lo0)
    # R1 explicit path list to R4, remove last item of list
    r1_r4_exp_path_list = copy.deepcopy(r1_r5_exp_path_list)
    for item in r1_r4_exp_path_list:
        del item[3]
    # R4 to R1 explicit path list
    r4_r1_exp_path_list = copy.deepcopy(r5_r1_exp_path_list)
    for item in r4_r1_exp_path_list:
        del item[0]
    # R1 to R5 = r5_r1_exp_path_list, R5 to R1 = r5_r1_exp_path_list
    # R1 to R4 = r1_r4_exp_path_list, R4 to R1 = r4_r1_exp_path_list
    # R1 to R5 backup paths
    r1_backup_lo = [r5_lo]
    r1_backup_main = ['15.1.1.2']
    r1_backup_bundle = ['15.1.2.2']
    r1_backup_list = [r1_backup_lo, r1_backup_main,
                      r1_backup_bundle]
    exp_names = ['loop0', 'main', 'sub', 'bundle']
    ##########################################
    #    CONFIG R1, R4, AND R5 INTFS TO TGEN
    ###########################################
    for rtr in uut_list:
        ip_addr_list = []
        intfs = []
        place_holder_cfg = ''
        i = 1
        if rtr == r1 or rtr == r4 or rtr == r5:
            if rtr == r1:
                intfs = r1_tgen_intfs
            if rtr == r4:
                intfs = r4_tgen_intfs
            if rtr == r5:
                intfs = r5_tgen_intfs
            # config main intf for L2 transport
            returnList = tcl.q.eval('::xr::config::ether '
                                    '-l2transport 1 '
                                    '-port_list {} '
                                    '-mask 24 '.format(tclstr(intfs)))
            place_holder_cfg += returnList.config_str
            if rtr == r1:
                rtr1_config_str += place_holder_cfg
                #rtr1_tgen1_cfg_intfs.append(returnList.intf_list)
            if rtr == r4:
                rtr4_config_str += place_holder_cfg
                #rtr4_tgen1_cfg_intfs.append(returnList.intf_list)
            if rtr == r5:
                rtr5_config_str += place_holder_cfg
                #rtr5_tgen1_cfg_intfs.append(returnList.intf_list)
        else:
            continue
    ##########################################
    #          CONFIG R1 TO R2
    ###########################################
    for rtr in uut_list:
        ip_addr_list = []
        ip_addr_list_v6 = []
        intfs = []
        if rtr == r1:
            num_intfs = len(r1_r2_intfs)
            intfs = r1_r2_intfs
            ip = 1
            for i in range(num_intfs):
                ip_addr_list.append('12.1.{}.1'.format(ip))
                ip_addr_list_v6.append('12::{}:1'.format(ip))
                ip += 1
        if rtr == r2:
            num_intfs = len(r2_r1_intfs)
            intfs = r2_r1_intfs
            ip = 1
            for i in range(num_intfs):
                ip_addr_list.append('12.1.{}.2'.format(ip))
                ip_addr_list_v6.append('12::{}:2'.format(ip))
                ip += 1
        # CONFIG MAIN INTERFACE FOR R1 AND R2
        if rtr == r1 or rtr == r2:
            # ADDING IPV4 ADDRESS
            returnList = tcl.q.eval('::xr::config::ether '
                                    '-port_list {} '
                                    '-ip_addr_list {} '.format(tclstr(intfs[0]),
                                                       tclstr(ip_addr_list[0])))
            # APPEND TO CONFIG STR
            if rtr == r1:
                rtr1_config_str += returnList.config_str
            if rtr == r2:
                rtr2_config_str += returnList.config_str

        else:
            continue
        # CONFIG RTR1 TO RTR2 SUB-INTERFACE
        if rtr == r1 or rtr == r2:
            # ADD IPV4 ADDRESS
            returnList = tcl.q.eval('::xr::config::ether '
                                    '-port_list {} '
                                    '-ip_addr_list {} '
                                    '-auto_negotiate 1 '
                                    '-mask 24 '
                                    '-transceiver_all 1 '
                                    '-efp_outer_encap_type dot1q '
                                    '-vlan_start_num 101 '
                                    '-subintf_start_num 101 '
                                    '-subintf_count 1 '
                                    '-vlan_mode efp '
                                    '-efp_outer_tag_type '
                                    'vlan-id'.format(tclstr(intfs[0]),
                                                     tclstr(ip_addr_list[1])))
            # APPEND TO CONFIG STR
            # CREATE CONFIG CONFIGURED INTF LIST FOR R1 AND R2
            if rtr == r1:
                rtr1_config_str += returnList.config_str
                rtr1_rtr2_cfg_intf_list.append(returnList.intf_list)
            if rtr == r2:
                rtr2_config_str += returnList.config_str
                rtr2_rtr1_cfg_intf_list.append(returnList.intf_list)
        else:
            continue
        # CONFIG BUNDLE INTERFACE RTR1 TO RTR2
        if rtr == r1 or rtr == r2:
            # ADD IPV4 ADDRESS
            returnList = tcl.q.eval('::xr::config::link_bundle '
                                    '-bundle_id 12 '
                                    '-bundle_count 1 '
                                    '-intf_per_bundle 2 '
                                    '-bundle_mode active '
                                    '-ip_addr_list {} '
                                    '-ip_mask_list 255.255.255.0 '
                                    '-intf_list {} '.format(
                                     tclstr(ip_addr_list[2]), tclstr(intfs[1:3])))
            # APPEND CONFIG STRING
            if rtr == r1:
                rtr1_config_str += returnList.config_str
                rtr1_rtr2_cfg_intf_list.append(returnList.bundle_intfs)
            if rtr == r2:
                rtr2_config_str += returnList.config_str
                rtr2_rtr1_cfg_intf_list.append(returnList.bundle_intfs)
        else:
            continue
    ##########################################
    #          CONFIG R1 TO R5
    ###########################################
    for rtr in uut_list:
        ip_addr_list = []
        ip_addr_list_v6 = []
        intfs = []
        if rtr == r1:
            num_intfs = len(r1_r5_intfs)
            intfs = r1_r5_intfs
            ip = 1
            for i in range(num_intfs):
                ip_addr_list.append('15.1.{}.1'.format(ip))
                ip_addr_list_v6.append('15::{}:1'.format(ip))
                ip += 1
        elif rtr == r5:
            num_intfs = len(r5_r1_intfs)
            intfs = r5_r1_intfs
            ip = 1
            for i in range(num_intfs):
                ip_addr_list.append('15.1.{}.2'.format(ip))
                ip_addr_list_v6.append('15::{}:2'.format(ip))
                ip += 1
        else:
            continue
        # CONFIG MAIN INTERFACE FOR R1 AND R5
        if rtr == r1 or rtr == r5:
            # ADD IPV4 ADDRESS
            returnList = tcl.q.eval('::xr::config::ether '
                                    '-port_list {} '
                                    '-ip_addr_list {} '.format(tclstr(intfs[0]),
                                                               tclstr(ip_addr_list[0])))
            # APPEND TO CONFIG STR
            if rtr == r1:
                rtr1_config_str += returnList.config_str
            if rtr == r5:
                rtr5_config_str += returnList.config_str
        else:
            continue
        if rtr == r1 or rtr == r5:
            # CONFIG IPV4 BUNDLE INTERFACE RTR1 TO RTR5
            returnList = tcl.q.eval('::xr::config::link_bundle '
                                    '-bundle_id 15 '
                                    '-bundle_count 1 '
                                    '-intf_per_bundle 2 '
                                    '-bundle_mode active '
                                    '-ip_addr_list {} '
                                    '-ip_mask_list 255.255.255.0 '
                                    '-intf_list {} '.format(
                                     tclstr(ip_addr_list[1]), tclstr(intfs[1:3])))
            # APPEND CONFIG STRING
            # GETTING LIST OF BUNDLE INTERFACES
            if rtr == r1:
                rtr1_config_str += returnList.config_str
                rtr1_rtr5_cfg_intf_list.append(returnList.bundle_intfs)
            if rtr == r5:
                rtr5_config_str += returnList.config_str
                rtr5_rtr1_cfg_intf_list.append(returnList.bundle_intfs)
        else:
            continue
    # SEGMENT_ROUTING MAPPING SERVER ON R1
    returnList = tcl.q.eval('::xr::config::segment_routing_mapping_server '
                            '-ip_addr_list 100.1.1.0 200.1.1.0 '
                            '-mask 30 '
                            '-range_flag 1 '
                            '-range_num 1000 '
                            '-prefix_sid_num 2001 '
                            '-incr_prefix_sid_num 2000')
    rtr1_config_str += returnList.config_str
    ##########################################
    #          CONFIG R2, R3, R4 interfaces
    ###########################################
    for rtr in uut_list[1:5]:
        back_to_back_flag = False  # some router need back to back ip configs
                                   # there for setting this flag will control
                                   # which routers need back to back ip configs
        place_holder_cfg = ''  # variable that is ued to pass the config to
                               # the coresponding router config string
        ip_addr_list_1 = []
        ip_addr_list_2 = []
        ip_addr_list_1_v6 = []
        ip_addr_list_2_v6 = []
        intfs_1 = []
        intfs_2 = []
        if rtr == r2:
            intfs_1 = r2_r3_intfs
            i = 1
            while i <= 3:
                ip_addr_list_1.append('23.1.{}.1'.format(i))
                ip_addr_list_1_v6.append('23::{}:1'.format(i))
                i += 1
        if rtr == r3:
            back_to_back_flag = True
            intfs_1 = r3_r2_intfs
            intfs_2 = r3_r4_intfs
            i = 1
            while i <= 3:
                ip_addr_list_1.append('23.1.{}.2'.format(i))
                ip_addr_list_2.append('34.1.{}.1'.format(i))
                ip_addr_list_1_v6.append('23::{}:2'.format(i))
                ip_addr_list_2_v6.append('34::{}:1'.format(i))
                i += 1
        if rtr == r4:
            back_to_back_flag = True
            intfs_1 = r4_r3_intfs
            intfs_2 = r4_r5_intfs
            i = 1
            while i <= 3:
                ip_addr_list_1.append('34.1.{}.2'.format(i))
                ip_addr_list_2.append('45.1.{}.1'.format(i))
                ip_addr_list_1_v6.append('34::{}:2'.format(i))
                ip_addr_list_2_v6.append('45::{}:1'.format(i))
                i += 1
        if rtr == r5:
            intfs_1 = r5_r4_intfs
            i = 1
            while i <= 3:
                ip_addr_list_1.append('45.1.{}.2'.format(i))
                ip_addr_list_1_v6.append('45::{}:2'.format(i))
                i += 1
        if back_to_back_flag is True:
            # ADDING IPV4 ADDRESS
            returnList = tcl.q.eval('::xr::config::ether '
                                    '-port_list {} '
                                    '-ip_addr_list {} '.format(
                                     tclstr(intfs_1[0]), tclstr(ip_addr_list_1[0])))
            place_holder_cfg += returnList.config_str
            # ADDING IPV4 ADDRESS
            returnList = tcl.q.eval('::xr::config::ether '
                                    '-port_list {} '
                                    '-ip_addr_list {} '.format(
                                     tclstr(intfs_2[0]), tclstr(ip_addr_list_2[0])))
            place_holder_cfg += returnList.config_str

        else:
            # ADDING IPV4 ADDRESS
            returnList = tcl.q.eval('::xr::config::ether '
                                    '-port_list {} '
                                    '-ip_addr_list {} '.format(
                                     tclstr(intfs_1[0]), tclstr(ip_addr_list_1[0])))
            place_holder_cfg += returnList.config_str

        # append to config str
        if rtr == r2:
            rtr2_config_str += place_holder_cfg
        if rtr == r3:
            rtr3_config_str += place_holder_cfg
        if rtr == r4:
            rtr4_config_str += place_holder_cfg
        if rtr == r5:
            rtr5_config_str += place_holder_cfg
    r1_all_intfs = rtr1_tgen1_cfg_intfs + [r1_r2_intfs[0]] + [r1_r5_intfs[0]] +\
                   rtr1_rtr2_cfg_intf_list + rtr1_rtr5_cfg_intf_list + ['loopback0']
    r2_all_intfs = [r2_r1_intfs[0]] + rtr2_rtr1_cfg_intf_list + \
                    r2_r3_intfs + ['loopback0']
    r3_all_intfs = r3_r2_intfs + r3_r4_intfs + ['loopback0']
    r4_all_intfs = rtr4_tgen1_cfg_intfs + r4_r3_intfs + r4_r5_intfs +\
                   ['loopback0']
    r5_all_intfs = rtr5_tgen1_cfg_intfs + [r5_r1_intfs[0]] +\
                   rtr5_rtr1_cfg_intf_list + r5_r4_intfs + ['loopback0']
    ##########################################
    # CONFIG ROUTING PROTOCOLS ON ALL ROUTERS
    ##########################################
    i = 1
    for rtr in uut_list:
        intfs = []
        place_holder_cfg = ''
        if rtr == r1:
            intfs = r1_all_intfs
            l2vpn_nbr_ip = [r4_lo, r5_lo]
            l2_vpn_intfs = [r1_tgen_intfs]
        if rtr == r2:
            intfs = r2_all_intfs
        if rtr == r3:
            intfs = r3_all_intfs
        if rtr == r4:
            intfs = r4_all_intfs
            l2vpn_nbr_ip = [r1_lo, r5_lo]
            l2_vpn_intfs = [r4_tgen_intfs]
        if rtr == r5:
            intfs = r5_all_intfs
            l2vpn_nbr_ip = [r1_lo, r4_lo]
            l2_vpn_intfs = [r5_tgen_intfs]
        # config loopback interfaces0
        looback_intf = '''
                       interface loopback0
                       ip address 192.168.{}.1/32
                       root'''.format(i)
        place_holder_cfg += looback_intf
        ##########################################
        #          CONFIG LDP ON ALL ROUTERS
        ###########################################
        returnList = tcl.q.eval('::xr::config::ldp ')
        place_holder_cfg += returnList.config_str
        ##################################
        # SELECT ROUTING PROTOCOL
        #################################
        if SrScriptArgs.routing_proto == 'ospf':
            ##########################################
            # CONFIG OSPF ON ALL ROUTERS
            ###########################################
            returnList = tcl.q.eval('::xr::config::ospf '
                                    '-process_id 1 '
                                    '-mpls_te '
                                    '-graceful_restart '
                                    '-mpls_te_router_id loopback0 '
                                    '-router_id 192.168.{i}.1 '
                                    '-area 0 '
                                    '-network point-to-point '
                                    '-intf_list {intfs} '
                                    '-sr_global_block 150000 180000 '
                                    '-sr_mpls 1 '
                                    '-intf_prefix_sid_flag 1 '
                                    '-intf_prefix_sid 100{i} '
                                    '-sr_forwarding_mpls 1 '
                                    '-nsr '.format(i=i,
                                                   intfs=tclstr(intfs)))
            place_holder_cfg += returnList.config_str
        else:
            ##########################################
            #          CONFIG ISIS ON ALL ROUTERS
            ###########################################
            returnList = tcl.q.eval('::xr::config::isis '
                                    '-process_name 1 '
                                    '-af_type ipv4 '
                                    '-nsf cisco '
                                    '-net_id 49.001.192.168.00{i}.001.00 '
                                    '-network_type point-to-point '
                                    '-intf_list {intfs} '
                                    '-mtr_level 2 '
                                    '-sr_global_block 50000 80000 '
                                    '-sr_mpls_sr_prefer 1 '
                                    '-sr_prefix_sid_map_rx 1 '
                                    '-sr_prefix_sid_map_adv_local  1 '
                                    '-microloop_avoidance_protected 1 '
                                    '-microloop_rib_delay 1 '
                                    '-microloop_delay_seconds 25000 '
                                    '-intf_prefix_sid_flag 1 '
                                    '-intf_prefix_sid  10{i} '
                                    '-mpls_te_rtr_id 192.168.{i}.1 '
                                    '-mpls_ldp_auto_config 1 '
                                    '-mpls_te_level 2-only '
                                    '-bfd_fast disable '
                                    '-is_type level-2-only'.format(i=i,
                                                           intfs=tclstr(intfs)))
            place_holder_cfg += returnList.config_str
        ##########################################
        # CONFIG MPLS-TE
        ###########################################
        intfs.remove('loopback0')  # not supported in mpls-te
        returnList = tcl.q.eval('::xr::config::mpls_te '
                                '-intf_list {} '.format(tclstr(intfs)))
        place_holder_cfg += returnList.config_str
        intfs.append('loopback0')  # adding back for other protocols
        ##########################################
        # CONFIG FRR TI-LFA ON R1
        ###########################################
        if rtr == r1 and SrScriptArgs.routing_proto == 'isis':
            returnList = tcl.q.eval('::xr::config::isis '
                                    '-process_name 1 '
                                    '-net_id 49.001.192.168.001.001.00 '
                                    '-intf_list {intfs} '
                                    '-frr_intf {intfs} '
                                    '-frr_type per-prefix '
                                    '-frr_ti_lfa_per_prefix_flag 1 '.format(intfs=tclstr(intfs)))
            place_holder_cfg += returnList.config_str
        if rtr == r1 or rtr == r4 or rtr == r5:
            ##########################################
            # CONFIG L2VPN BRIDGE DOMAIN
            ###########################################
            for ip in l2vpn_nbr_ip:
                returnList = tcl.q.eval('::xr::config::l2vpn '
                                        '-port_list {} '
                                        '-switching_mode bridge-group '
                                        '-bridge_domain_count 1 '
                                        '-neighbor_list {} '
                                        '-split_horizon '
                                        '-bridge_group_name sr_vpls '
                                        '-interfaces_per_bd 1 '
                                        '-neighbors_per_domain 1 '
                                        '-pw_start 1'.format(tclstr(l2_vpn_intfs),
                                                             tclstr(ip)))
                place_holder_cfg += returnList.config_str
        ###############################
        # CONFIG SR TUNNELS
        ###############################
        if rtr == r1:
            # R1 TO R5 dynamic + explicit primary tunnels
            sr_cfg = config_sr_tunnels(tun_dst=r5_lo, tunnel_id=151,
                                       num_dynamic_tuns=2, exp_list_names=exp_names,
                                       exp_ip_list=r1_r5_exp_path_list)
            place_holder_cfg += sr_cfg
            # R1 TO R4 dynamic + explicit primary tunnels
            sr_cfg = config_sr_tunnels(tun_dst=r4_lo, tunnel_id=141,
                                       num_dynamic_tuns=2,
                                       exp_list_names=exp_names,
                                       exp_ip_list=r1_r4_exp_path_list)
            place_holder_cfg += sr_cfg
            # creating list of tunnels
            a = 151
            b = 141
            r1_r5_tunnel_list = []
            r1_r4_tunnel_list = []
            while a <= 156:
                tunnel_intf_r1_r5 = 'tunnel-te{}'.format(a)
                tunnel_intf_r1_r4 = 'tunnel-te{}'.format(b)
                r1_r5_tunnel_list.append(tunnel_intf_r1_r5)
                r1_r4_tunnel_list.append(tunnel_intf_r1_r4)
                a += 1
                b += 1
        if rtr == r4:
            # R4 TO R1 dynamic + explicit primary tunnels
            sr_cfg = config_sr_tunnels(tun_dst=r1_lo, tunnel_id=141,
                                       num_dynamic_tuns=2,
                                       exp_list_names=exp_names,
                                       exp_ip_list=r4_r1_exp_path_list)
            place_holder_cfg += sr_cfg
        if rtr == r5:
            # R5 TO R1 dynamic + explicit primary tunnels
            sr_cfg = config_sr_tunnels(tun_dst=r1_lo, tunnel_id=151,
                                       num_dynamic_tuns=2,
                                       exp_list_names=exp_names,
                                       exp_ip_list=r5_r1_exp_path_list)
            place_holder_cfg += sr_cfg
        if rtr == r1:
            rtr1_config_str += place_holder_cfg
        if rtr == r2:
            rtr2_config_str += place_holder_cfg
        if rtr == r3:
            rtr3_config_str += place_holder_cfg
        if rtr == r4:
            rtr4_config_str += place_holder_cfg
        if rtr == r5:
            rtr5_config_str += place_holder_cfg
        i += 1
    # create list of all router config_str
    config_list = [rtr1_config_str, rtr2_config_str, rtr3_config_str,
                   rtr4_config_str, rtr5_config_str]
    #####################################
    # CONNECT TO IXIA
    ####################################
    ixia = Ixia()
    ixia.connect(device=testbed.devices["ixia"],
                 tcl_server=testbed.devices['ixia'].connections.ixia['ip'],
                 port_list=tgen_handle_list,
                 username='ciscoUser',
                 ixnetwork_tcl_server=testbed.devices['ixia'].connections.ixia['tcl_server'],
                 reset=1)
    ######################################
    # CONFIG IXIA INTERFACE TO R1, R4,R5
    #####################################
    tgen_r1_port1 = ixia.interface_config(port_handle=tgen_port_handle1,
                                          phy_mode='fiber',
                                          intf_ip_addr='21.1.1.1',
                                          speed=SrScriptArgs.r1_tgen1_speed,
                                          gateway='21.1.1.5')
    tgen_r1_port1 = tgen_r1_port1.interface_handle
    tgen_r4_port1 = ixia.interface_config(port_handle=tgen_port_handle2,
                                          phy_mode='fiber',
                                          intf_ip_addr='21.1.1.4',
                                          speed=SrScriptArgs.r4_tgen1_speed,
                                          gateway='21.1.1.1')
    tgen_r4_port1 = tgen_r4_port1.interface_handle
    tgen_r5_port1 = ixia.interface_config(port_handle=tgen_port_handle3,
                                          phy_mode='fiber',
                                          intf_ip_addr='21.1.1.5',
                                          speed=SrScriptArgs.r5_tgen1_speed,
                                          gateway='21.1.1.1')
    tgen_r5_port1 = tgen_r5_port1.interface_handle
    @aetest.subsection
    def connect(self, uut_list=uut_list):
        """ common setup subsection: connecting devices """
        # Connect to the device
        log.info(banner('CONNECTING TO ROUTERS'))
        for rtr in uut_list:
            rtr.connect()
            # Make sure that the connection went fine
            if not hasattr(rtr, 'execute'):
                self.failed()
            if rtr.execute != rtr.connectionmgr.default.execute:
                self.failed()
            # loading stratup config
            startup_result = tcl.q.eval('::xr::unconfig::router '
                                        '-device {} '
                                        '-load_file {}'
                                        .format(rtr.handle,
                                        SrScriptArgs.startup_config))
            if startup_result == 1:
                log.info('''successfully loaded startup config for {}
                         '''.format(rtr.handle))
            else:
                log.error('''failed to load startup config for {}
                          '''.fromat(rtr.handle))
    @aetest.subsection
    def pre_router_check(self, uut_list=uut_list):
        tcl.q.eval('pre_router_check {} '.format(uut_list[0].handle))
    @aetest.subsection
    def apply_configs(self, uut_list=uut_list):
        log.info(banner('applying config on router'))
        ######################################
        # APPLY CONFIGS ON ALL ROUTERS
        ######################################
        i = 0
        j = 1
        for rtr in uut_list:
            log.info(banner('applying config on R{} {}'.format(j, rtr)))
            try:
                rtr.configure(self.config_list[i])
            except:
                log.error('Invalid CLI given: {}'.format(self.config_list[i]))
                log.error('Error with cli')
                log.error(sys.exc_info())
            i += 1
            j += 1
        time.sleep(20)
    @aetest.subsection
    def verify_control_plane(self, uut_list=uut_list):
        #######################################
        # VERIFY ISIS AND OSPF
        #######################################
        for rtr in uut_list:
            routing_intfs = ''
            l2vpn_nbr_ip = []
            if rtr == self.r1:
                self.r1_all_intfs.remove('loopback0')  # not counted as isis adj
                routing_intfs = self.r1_all_intfs[:]  # create 2nd list without L0
                self.r1_all_intfs.append('loopback0')
            if rtr == self.r2:
                self.r2_all_intfs.remove('loopback0')
                routing_intfs = self.r2_all_intfs[:]
                self.r2_all_intfs.append('loopback0')
            if rtr == self.r3:
                self.r3_all_intfs.remove('loopback0')
                routing_intfs = self.r3_all_intfs[:]
                self.r3_all_intfs.append('loopback0')
            if rtr == self.r4:
                self.r4_all_intfs.remove('loopback0')
                routing_intfs = self.r4_all_intfs[:]
                self.r4_all_intfs.append('loopback0')
            if rtr == self.r5:
                self.r5_all_intfs.remove('loopback0')
                routing_intfs = self.r5_all_intfs[:]
                self.r5_all_intfs.append('loopback0')
            expected_num_intfs = len(routing_intfs)
            if SrScriptArgs.routing_proto == 'isis':
                # calling verify fucntion to verify isis adjacency
                isis_result = Verify.routing_protocol(rtr, expected_num_intfs,
                                                      protocol='isis')
                if isis_result != 0:
                    self.failed('isis verify failed on {}'.format(rtr))
            if SrScriptArgs.routing_proto == 'ospf':
                # calling verify fucntion to verify isis adjacency
                ospf_result = Verify.routing_protocol(rtr, expected_num_intfs,
                                                      protocol='ospf')
                if ospf_result != 0:
                    self.failed('isis verify failed on {}'.format(rtr))
        #######################################
        # VERIFY L2VPN IS UP
        #######################################
        for rtr in uut_list:
            if rtr == self.r1:
                l2vpn_nbr_ip = [self.r4_lo, self.r5_lo]
            if rtr == self.r4:
                l2vpn_nbr_ip = [self.r1_lo, self.r5_lo]
            if rtr == self.r5:
                l2vpn_nbr_ip = [self.r1_lo, self.r4_lo]
            if rtr == self.r1 or rtr == self.r4 or rtr == self.r5:
                l2vpn_result = Verify.l2vpn(rtr, l2vpn_nbr_ip)
                # verify results of isis and ospf
                if l2vpn_result != 0:
                    self.failed('l2vpn verify failed on {}'.format(rtr))
        #######################################
        # VERIFY TE-TUNNEL'S ARE UP
        #######################################
        for rtr in uut_list:
            if rtr == self.r1 or rtr == self.r4 or rtr == self.r5:
                te_result = Verify.te_tunnels(rtr=rtr)
            if te_result != 0:
                self.failed('''failed to bring up tunnels
                               or rtr {}'''.format(rtr))
    @aetest.subsection
    def verify_ixia(self):
        #############################################
        # CONFIG IXIA TRAFFIC STREAM
        ############################################
        # stream R1 to R5 and R5 back to R1
        s1 = self.ixia.traffic_config(mode='create',
                                      traffic_generator='ixnetwork_540',
                                      name='r1_r5_ipv4_known_unicast',
                                      length_mode='fixed',
                                      l3_length='1000',
                                      transmit_mode='single_burst',
                                      pkts_per_burst='100000',
                                      l3_protocol='ipv4',
                                      track_by='endpoint_pair traffic_item',
                                      ip_src_addr='21.1.1.1',
                                      ip_dst_addr='21.1.1.5',
                                      bidirectional=1,
                                      src_dest_mesh='one_to_one',
                                      emulation_src_handle=self.tgen_port_handle1,
                                      emulation_dst_handle=self.tgen_port_handle3,
                                      circuit_endpoint_type='ipv4',
                                      rate_pps=10000)
        s1_id = s1.stream_id
        # stream R1 to R4 and R4 back to R1
        s2 = self.ixia.traffic_config(mode='create',
                                      traffic_generator='ixnetwork_540',
                                      name='r1_r4_ipv4_known_unicast',
                                      transmit_mode='single_burst',
                                      pkts_per_burst='100000',
                                      l3_protocol='ipv4',
                                      length_mode='fixed',
                                      l3_length='1000',
                                      track_by='endpoint_pair traffic_item',
                                      bidirectional=1,
                                      src_dest_mesh='one_to_one',
                                      emulation_src_handle=self.tgen_port_handle1,
                                      emulation_dst_handle=self.tgen_port_handle2,
                                      circuit_endpoint_type='ipv4',
                                      rate_pps=10000,)
        s2_id = s2.stream_id
        # mcast traffic unkown src and dst mac
        s3 = self.ixia.traffic_config(mode='create',
                                      traffic_generator='ixnetwork_540',
                                      convert_to_raw='1',
                                      name='r1_mcast_traffic',
                                      ip_src_addr='1.1.1.1',
                                      ip_dst_addr='2.2.2.2',
                                      mac_src='aaaa.aaaa.aaaa',
                                      mac_dst='bbbb.bbbb.bbbb',
                                      transmit_mode='single_burst',
                                      pkts_per_burst='100000',
                                      l3_protocol='ipv4',
                                      length_mode='fixed',
                                      l3_length='1000',
                                      track_by='endpoint_pair traffic_item',
                                      bidirectional=0,
                                      src_dest_mesh='one_to_one',
                                      emulation_src_handle=self.tgen_port_handle1,
                                      emulation_dst_handle=[self.tgen_port_handle2,
                                                            self.tgen_port_handle3],
                                      circuit_endpoint_type='ipv4',
                                      rate_pps=5000,)
        s3_id = s3.stream_id
        # bcast traffic dst mac as ffff.ffff.ffff
        s4 = self.ixia.traffic_config(mode='create',
                                      traffic_generator='ixnetwork_540',
                                      convert_to_raw='1',
                                      name='r1_bcast_traffic',
                                      ip_src_addr='1.1.1.1',
                                      ip_dst_addr='2.2.2.2',
                                      mac_src='aaaa.aaaa.aaaa',
                                      mac_dst='ffff.ffff.ffff',
                                      transmit_mode='single_burst',
                                      pkts_per_burst='100000',
                                      l3_protocol='ipv4',
                                      length_mode='fixed',
                                      l3_length='1000',
                                      track_by='endpoint_pair traffic_item',
                                      bidirectional=0,
                                      src_dest_mesh='one_to_one',
                                      emulation_src_handle=self.tgen_port_handle1,
                                      emulation_dst_handle=[self.tgen_port_handle2,
                                                            self.tgen_port_handle3],
                                      circuit_endpoint_type='ipv4',
                                      rate_pps=5000,)
        s4_id = s4.stream_id
        # unkown unicast traffic known src mac and unkown dst mac
        s5 = self.ixia.traffic_config(mode='create',
                                      traffic_generator='ixnetwork_540',
                                      convert_to_raw='1',
                                      name='r1_unkown_unicast_traffic',
                                      ip_src_addr='1.1.1.1',
                                      ip_dst_addr='2.2.2.2',
                                      mac_src='0000.0000.0001',
                                      mac_dst='cccc.cccc.cccc',
                                      transmit_mode='single_burst',
                                      pkts_per_burst='100000',
                                      l3_protocol='ipv4',
                                      length_mode='fixed',
                                      l3_length='1000',
                                      track_by='endpoint_pair traffic_item',
                                      bidirectional=0,
                                      src_dest_mesh='one_to_one',
                                      emulation_src_handle=self.tgen_port_handle1,
                                      emulation_dst_handle=[self.tgen_port_handle2,
                                                            self.tgen_port_handle3],
                                      circuit_endpoint_type='ipv4',
                                      rate_pps=5000,)
        s5_id = s5.stream_id
        global stream_list
        stream_list = [s1_id, s2_id, s3_id, s4_id, s5_id]
        # VERIFY APR ON TGEN INTERFACES
        for tgen_intf in self.port_handle_list:
            result = self.ixia.interface_config(port_handle=tgen_intf,
                                                arp_send_req='1')
            arp_result = result[tgen_intf].arp_request_success
            time.sleep(5)
            if int(arp_result) == 1:
                log.info('PASS ARP WAS SUCCESSFUL ON {}'.format(tgen_intf))
            else:
                self.failed('ARP FAILED ON {}'.format(tgen_intf))
#######################################################################
#                          TESTCASE BLOCK                             #
#######################################################################
class Sr_te_path_sr(aetest.Testcase):
    """Verify SR using path option segment routing."""
    debug = 0
    @aetest.setup
    def setup(self):
        """Testcase setup."""
        sr = common_setup()
        # get linecard location
        global uut_lc
        uut_lc = tcl.eval('rtr_show_utils::intf_convert '
                          '-device {} '
                          '-intf {} '
                          '-return node_id '.format(sr.r1.handle,
                                                    sr.r1_tgen_intfs[0]))
        r1_r5_int = [tclstr(sr.rtr1_rtr5_cfg_intf_list), sr.r1_r5_intfs[0]]
        for intf in r1_r5_int:
            sr.r1.configure('interface {} shutdown'.format(intf))
        sr.r1.execute('show mpls forwarding tunnels')
        # remove autoroute announce from all tunnels
        for r1_r5_tun, r1_r4_tun in itertools.zip_longest(sr.r1_r5_tunnel_list,
                                                          sr.r1_r4_tunnel_list):
            sr.r1.configure('''interface {}
                            no autoroute announce'''.format(r1_r5_tun))
            sr.r1.configure('''interface {}
                            no autoroute announce'''.format(r1_r4_tun))
        # Adding autoroute announce back to single tunnel
        sr.r1.configure('''interface {}
                        autoroute announce'''.format(sr.r1_r5_tunnel_list[0]))
        sr.r1.configure('''interface {}
                        autoroute announce'''.format(sr.r1_r4_tunnel_list[0]))
        # add autoroute announce for sr tunnel
    @aetest.test
    def test(self):
        """Testcase execution."""
        log.info("Testcase sr_te_path_sr")
        sr = common_setup()
        self.debug = 0
        # 1. CLEAR COUNTERS
        Clear.counters(sr.uut_list)
        # 2. VERIFY FWD OVER TUNNEL
        result = Verify.route(sr.r1, [sr.r4_lo, sr.r5_lo],
                             [sr.r1_r4_tunnel_list[0], sr.r1_r5_tunnel_list[0]])
        if result == 1:
            self.failed('tunnel fwd was not as expected')
        # 3. SEND TRAFFIC
        ixia_result = Verify.ixia_traffic_rx()
        if ixia_result == 1:
            self.failed('traffic failed')
        # 4. VERIFY TRAFFIC STATS
        result = Verify.interface_counters(sr.r1.handle,
                                           [sr.r1_r4_tunnel_list[0],
                                           sr.r1_r5_tunnel_list[0]])
        if result == 1:
            self.failed('interface traffic accounting failed')
        # removing aa from tun 141 and 151. Also adding aa to tun 142 and 152
        autoroute_announce(sr.r1,
                           [sr.r1_r4_tunnel_list[0], sr.r1_r5_tunnel_list[0]],
                           [sr.r1_r4_tunnel_list[1], sr.r1_r5_tunnel_list[1]])
    @aetest.cleanup
    def cleanup(self):
        """Testcase cleanup."""
        # COLLECT DEBUG LOGS
        sr = common_setup()
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])
class Sr_te_path_dynamic_sr(aetest.Testcase):
    """Verify SR using path option dynamic segment routing."""
    debug = 0
    @aetest.setup
    def setup(self):
        """Testcase setup."""
    @aetest.test
    def test(self):
        """Testcase execution."""
        sr = common_setup()
        # 1. CLEAR COUNTERS
        Clear.counters(sr.uut_list)
        # 2. VERIFY FWD OVER TUNNEL
        result = Verify.route(sr.r1, [sr.r4_lo, sr.r5_lo],
                             [sr.r1_r4_tunnel_list[1], sr.r1_r5_tunnel_list[1]])
        if result == 1:
            self.debug = 1
            self.failed('tunnel fwd was not as expected')
        # 3. SEND TRAFFIC
        ixia_result = Verify.ixia_traffic_rx()
        if ixia_result == 1:
            self.debug = 1
            self.failed('traffic failed')
        # 4. VERIFY TRAFFIC STATS
        result = Verify.interface_counters(sr.r1.handle,
                                           [sr.r1_r4_tunnel_list[1],
                                           sr.r1_r5_tunnel_list[1]])
        if result == 1:
            self.debug = 1
            self.failed('interface traffic accounting failed')
        # removing aa from tun 142 and 152. Also adding aa to tun 143 and 153
        autoroute_announce(sr.r1,
                           [sr.r1_r4_tunnel_list[1], sr.r1_r5_tunnel_list[1]],
                           [sr.r1_r4_tunnel_list[2], sr.r1_r5_tunnel_list[2]])
    @aetest.cleanup
    def cleanup(self):
        """Testcase cleanup."""
        sr = common_setup()
        # COLLECT DEBUG LOGS
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])
class Sr_te_path_exp_node_sid(aetest.Testcase):
    """Verify SR using explicit path via the nodal sid's."""
    debug = 0
    @aetest.setup
    def setup(self):
        """Testcase setup."""
    @aetest.test
    def test(self):
        """Testcase execution."""
        sr = common_setup()
        # 1. CLEAR COUNTERS
        Clear.counters(sr.uut_list)
        # 2. VERIFY FWD OVER TUNNEL
        result = Verify.route(sr.r1, [sr.r4_lo, sr.r5_lo],
                             [sr.r1_r4_tunnel_list[2], sr.r1_r5_tunnel_list[2]])
        if result == 1:
            self.debug = 1
            self.failed('tunnel fwd was not as expected')
        # 3. SEND TRAFFIC
        ixia_result = Verify.ixia_traffic_rx()
        if ixia_result == 1:
            self.debug = 1
            self.failed('traffic failed')
        # 4. VERIFY TRAFFIC STATS
        result = Verify.interface_counters(sr.r1.handle,
                                           [sr.r1_r4_tunnel_list[2],
                                           sr.r1_r5_tunnel_list[2]])
        if result == 1:
            self.debug = 1
            self.failed('interface traffic accounting failed')
        # removing aa from tun 143 and 153. Also adding aa to tun 144 and 154
        autoroute_announce(sr.r1,
                           [sr.r1_r4_tunnel_list[2], sr.r1_r5_tunnel_list[2]],
                           [sr.r1_r4_tunnel_list[3], sr.r1_r5_tunnel_list[3]])
    @aetest.cleanup
    def cleanup(self):
        """Testcase cleanup."""
        sr = common_setup()
        # COLLECT DEBUG LOGS
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])
class Sr_te_path_exp_adj_sid_via_main_intf(aetest.Testcase):
    """Verify SR using adjacency sid via the main interface."""
    debug = 0
    @aetest.setup
    def setup(self):
        """Testcase setup."""
    @aetest.test
    def test(self):
        """Testcase execution."""
        sr = common_setup()
        # 1. CLEAR COUNTERS
        Clear.counters(sr.uut_list)
        # 2. VERIFY FWD OVER TUNNEL
        result = Verify.route(sr.r1, [sr.r4_lo, sr.r5_lo],
                             [sr.r1_r4_tunnel_list[3], sr.r1_r5_tunnel_list[3]])
        if result == 1:
            self.debug = 1
            self.failed('tunnel fwd was not as expected')
        # 3. SEND TRAFFIC
        ixia_result = Verify.ixia_traffic_rx()
        if ixia_result == 1:
            self.debug = 1
            self.failed('traffic failed')
        # 4. VERIFY TRAFFIC STATS
        result = Verify.interface_counters(sr.r1.handle,
                                           [sr.r1_r4_tunnel_list[3],
                                           sr.r1_r5_tunnel_list[3]])
        if result == 1:
            self.debug = 1
            self.failed('interface traffic accounting failed')
        # removing aa from tun 144 and 154. Also adding aa to tun 145 and 155
        autoroute_announce(sr.r1,
                           [sr.r1_r4_tunnel_list[3], sr.r1_r5_tunnel_list[3]],
                           [sr.r1_r4_tunnel_list[4], sr.r1_r5_tunnel_list[4]])
    @aetest.cleanup
    def cleanup(self):
        """Testcase cleanup."""
        sr = common_setup()
        # COLLECT DEBUG LOGS
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])
class Sr_te_path_exp_adj_sid_via_sub_intf(aetest.Testcase):
    """Verify SR using adjacency sid via the sub-interface."""
    debug = 0
    @aetest.setup
    def setup(self):
        """Testcase setup."""
    @aetest.test
    def test(self):
        """Testcase execution."""
        sr = common_setup()
        # 1. CLEAR COUNTERS
        Clear.counters(sr.uut_list)
        # 2. VERIFY FWD OVER TUNNEL
        result = Verify.route(sr.r1, [sr.r4_lo, sr.r5_lo],
                             [sr.r1_r4_tunnel_list[4], sr.r1_r5_tunnel_list[4]])
        if result == 1:
            self.debug = 1
            self.failed('tunnel fwd was not as expected')
        # 3. SEND TRAFFIC
        ixia_result = Verify.ixia_traffic_rx()
        if ixia_result == 1:
            self.debug = 1
            self.failed('traffic failed')
        # 4. VERIFY TRAFFIC STATS
        result = Verify.interface_counters(sr.r1.handle,
                                           [sr.r1_r4_tunnel_list[4],
                                           sr.r1_r5_tunnel_list[4]])
        if result == 1:
            self.debug = 1
            self.failed('interface traffic accounting failed')
        # removing aa from tun 144 and 154. Also adding aa to tun 145 and 155
        autoroute_announce(sr.r1,
                           [sr.r1_r4_tunnel_list[4], sr.r1_r5_tunnel_list[4]],
                           [sr.r1_r4_tunnel_list[5], sr.r1_r5_tunnel_list[5]])
    @aetest.cleanup
    def cleanup(self):
        """Testcase cleanup."""
        sr = common_setup()
        # COLLECT DEBUG LOGS
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])
class Sr_te_path_exp_adj_sid_via_bundle_intf(aetest.Testcase):
    '''Verify SR using adjacency sid via the bundle interface'''
    debug = 0
    @aetest.setup
    def setup(self):
        """Testcase setup."""
    @aetest.test
    def test(self):
        """Testcase execution."""
        sr = common_setup()
        # 1. CLEAR COUNTERS
        Clear.counters(sr.uut_list)
        # 2. VERIFY FWD OVER TUNNEL
        result = Verify.route(sr.r1, [sr.r4_lo, sr.r5_lo],
                             [sr.r1_r4_tunnel_list[5], sr.r1_r5_tunnel_list[5]])
        if result == 1:
            self.debug = 1
            self.failed('tunnel fwd was not as expected')
        # 3. SEND TRAFFIC
        ixia_result = Verify.ixia_traffic_rx()
        if ixia_result == 1:
            self.debug = 1
            self.failed('traffic failed')
        # 4. VERIFY TRAFFIC STATS
        result = Verify.interface_counters(sr.r1.handle,
                                           [sr.r1_r4_tunnel_list[5],
                                           sr.r1_r5_tunnel_list[5]])
        if result == 1:
            self.debug = 1
            self.failed('interface traffic accounting failed')
    @aetest.cleanup
    def cleanup(self):
        """Testcase cleanup."""
        sr = common_setup()
        # COLLECT DEBUG LOGS
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])
class Rsp_failover_fail_back(aetest.Testcase):
    """Verify SR after RSP failover then failback."""
    debug = 0
    @aetest.setup
    def setup(self):
        """Testcase setup."""
        sr = common_setup()
        # selecting random number for tunnel
        # removing aa from tun 146 and 156. adding aa to random selected tunnel
        autoroute_announce(sr.r1,
                           [sr.r1_r4_tunnel_list[5], sr.r1_r5_tunnel_list[5]],
                           [sr.r1_r4_tunnel_list[random_tun_num],
                           sr.r1_r5_tunnel_list[random_tun_num]])
    @aetest.test
    def test(self):
        """Testcase execution."""
        sr = common_setup()
        attempts = 2
        i = 1
        while i <= attempts:
            log.info(banner('RSP SWITCHOVER ATTEMPT {}'.format(i)))
            # 1. CLEAR COUNTERS
            Clear.counters(sr.uut_list)
            # 2. VERIFY FWD OVER TUNNEL
            result = Verify.route(sr.r1, [sr.r4_lo, sr.r5_lo],
                                 [sr.r1_r4_tunnel_list[random_tun_num],
                                 sr.r1_r5_tunnel_list[random_tun_num]])
            if result == 1:
                self.debug = 1
                self.failed('tunnel fwd was not as expected')
            # executing switchover
            fo_status = tcl.q.eval('::xr::utils::switchover_time '
                                   '-device {} '
                                   '-switchover_type rsp_switchover '
                                   '-data_check 0'.format(sr.r1.handle))
            # 3. SEND TRAFFIC
            ixia_result = Verify.ixia_traffic_rx()
            if ixia_result == 1:
                self.debug = 1
                self.failed('traffic failed')
            if fo_status == 0:
                self.debug = 1
                self.failed('switchover failed')
            # 4. VERIFY TRAFFIC STATS
            result = Verify.interface_counters(sr.r1.handle,
                                               [sr.r1_r4_tunnel_list[random_tun_num],
                                               sr.r1_r5_tunnel_list[random_tun_num]])
            if result == 1:
                self.debug = 1
                self.failed('interface traffic accounting failed')
            i += 1
    @aetest.cleanup
    def cleanup(self):
        """Testcase cleanup."""
        sr = common_setup()
        # COLLECT DEBUG LOGS
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])
class Process_restarts_rsp(aetest.Testcase):
    """Verify SR after restarting the RSP process."""
    debug = 0
    p_index = 0
    @aetest.setup
    def setup(self):
        """Testcase setup."""
    @aetest.test.loop(uids=SrScriptArgs.rsp_process_list)
    @aetest.test
    def test(self):
        """Testcase execution."""
        sr = common_setup()
        process = SrScriptArgs.rsp_process_list
        log.info(banner('RSP RESTART PROCESS {}'.format(process[self.p_index])))
        # 1. CLEAR COUNTERS
        Clear.counters(sr.uut_list)
        # 2. VERIFY FWD OVER TUNNEL
        result = Verify.route(sr.r1, [sr.r4_lo, sr.r5_lo],
                             [sr.r1_r4_tunnel_list[random_tun_num],
                             sr.r1_r5_tunnel_list[random_tun_num]])
        if result == 1:
            self.debug = 1
            self.failed('tunnel fwd was not as expected')
        # RESTARTING PROCESS ON RSP
        restart_status = tcl.q.eval('::xr::utils::restart_process '
                                    '-process {} '
                                    '-restart_type restart '
                                    '-device {} '.format(process[self.p_index],
                                                         sr.r1.handle))
        # verify if process restart returned to run state
        if restart_status == 0:
            self.debug = 1
            self.failed('''process restart failed for {}
                        '''.format(process[self.p_index]))
        # 3. SEND TRAFFIC
        ixia_result = Verify.ixia_traffic_rx()
        if ixia_result == 1:
            self.debug = 1
            self.failed('traffic failed')
        # 4. VERIFY TRAFFIC STATS
        result = Verify.interface_counters(sr.r1.handle,
                                           [sr.r1_r4_tunnel_list[random_tun_num],
                                           sr.r1_r5_tunnel_list[random_tun_num]])
        if result == 1:
            self.debug = 1
            self.failed('interface traffic accounting failed')
        self.p_index += 1
    @aetest.cleanup
    def cleanup(self):
        """Testcase cleanup."""
        sr = common_setup()
        # COLLECT DEBUG LOGS
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])
class Process_restarts_lc(aetest.Testcase):
    """Verify SR after restarting the linecard process."""
    debug = 0
    p_index = 0
    @aetest.setup
    def setup(self):
        """Testcase setup."""
    @aetest.test.loop(uids=SrScriptArgs.lc_process_list)
    @aetest.test
    def test(self):
        """Testcase execution."""
        sr = common_setup()
        process = SrScriptArgs.lc_process_list
        log.info(banner('LC RESTART PROCESS {}'.format(process[self.p_index])))
        # 1. CLEAR COUNTERS
        Clear.counters(sr.uut_list)
        # 2. VERIFY FWD OVER TUNNEL
        result = Verify.route(sr.r1, [sr.r4_lo, sr.r5_lo],
                              [sr.r1_r4_tunnel_list[random_tun_num],
                              sr.r1_r5_tunnel_list[random_tun_num]])
        if result == 1:
            self.debug = 1
            self.failed('tunnel fwd was not as expected')
        # RESTARTING LC PROCESS
        restart_status = tcl.eval('::xr::utils::restart_process '
                                  '-process {} '
                                  '-restart_type restart '
                                  '-device {} '
                                  '-process_location {} '
                                  .format(process[self.p_index], sr.r1.handle,
                                          uut_lc))
        # VERIFY IF PROCESS RESTART RETURNED TO RUN STATE
        if restart_status == 0:
            self.debug = 1
            self.failed('''process restart failed for {}
                        '''.format(process))
        # 3. SEND TRAFFIC
        ixia_result = Verify.ixia_traffic_rx()
        if ixia_result == 1:
            self.debug = 1
            self.failed('traffic failed')
        # 4. VERIFY TRAFFIC STATS
        result = Verify.interface_counters(sr.r1.handle,
                                         [sr.r1_r4_tunnel_list[random_tun_num],
                                         sr.r1_r5_tunnel_list[random_tun_num]])
        if result == 1:
            self.debug = 1
            self.failed('interface traffic accounting failed')
        self.p_index += 1
    @aetest.cleanup
    def cleanup(self):
        """Testcase cleanup."""
        sr = common_setup()
        # COLLECT DEBUG LOGS
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])
class Lc_reload(aetest.Testcase):
    """Verify SR after reloading the linecard."""
    debug = 0
    @aetest.setup
    def setup(self):
        """Testcase setup."""
    @aetest.test
    def test(self):
        """Testcase execution."""
        sr = common_setup()
        # reloading lc
        lc_result = tcl.q.eval('::xr::utils::switchover_time '
                               '-device {} '
                               '-data_check 0 '
                               '-switchover_type hw_module '
                               '-return_state_timeout 300 '
                               '-hw_module_location {} '
                               .format(sr.r1.handle, uut_lc))
        time.sleep(30)
        # verify if lc reload was successful
        if lc_result == 0:
            self.debug = 1
            self.failed('lc reload failed')
        # verify l2vpn is up
        l2vpn_result = Verify.l2vpn(sr.r1, [sr.r4_lo, sr.r5_lo])
        if l2vpn_result != 0:
            self.debug = 1
            self.failed('l2vpn verify failed on {}'.format(sr.r1))
        # verify igp is up
        isis_result = Verify.routing_protocol(sr.r1, 3,
                                              protocol=proto)
        if isis_result != 0:
            self.debug = 1
            self.failed('isis verify failed on {}'.format(sr.r1))
        # verify tunnel is up
        tun_result = Verify.te_tunnels(sr.r1, 0,
                                       [sr.r1_r4_tunnel_list[random_tun_num],
                                        sr.r1_r5_tunnel_list[random_tun_num]])
        if tun_result == 1:
            self.debug = 1
            self.failed('tunnels did not come up')
        # 1. CLEAR COUNTERS
        Clear.counters(sr.uut_list)
        # 2. VERIFY FWD OVER TUNNEL
        result = Verify.route(sr.r1, [sr.r4_lo, sr.r5_lo],
                              [sr.r1_r4_tunnel_list[random_tun_num],
                              sr.r1_r5_tunnel_list[random_tun_num]])
        if result == 1:
            self.debug = 1
            self.failed('tunnel fwd was not as expected')
        # 3. SEND TRAFFIC
        ixia_result = Verify.ixia_traffic_rx()
        if ixia_result == 1:
            self.debug = 1
            self.failed('traffic failed')
        # 4. VERIFY TRAFFIC STATS
        result = Verify.interface_counters(sr.r1.handle,
                                           [sr.r1_r4_tunnel_list[random_tun_num],
                                           sr.r1_r5_tunnel_list[random_tun_num]])
        if result == 1:
            self.debug = 1
            self.failed('interface traffic accounting failed')
    @aetest.cleanup
    def cleanup(self):
        """Testcase cleanup."""
        sr = common_setup()
        # COLLECT DEBUG LOGS
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])
class Tunnel_flap(aetest.Testcase):
    """Verify SR while flapping the SR tuneles."""
    debug = 0
    @aetest.setup
    def setup(self):
        """Testcase setup."""
    @aetest.test
    def test(self):
        """Testcase execution."""
        sr = common_setup()
        tun1 = sr.r1_r4_tunnel_list[random_tun_num]
        tun2 = sr.r1_r5_tunnel_list[random_tun_num]
        # remove loopbacks from rtr4 and rtr5
        attempts = 5
        i = 1
        while i <= attempts:
            log.info(banner('tunnel flap attempt {}'.format(i)))
            print(sr.r1.configure('interface {} shutdown'.format(tun1)))
            print(sr.r1.configure('interface {} shutdown'.format(tun2)))
            print(sr.r1.configure('''interface {}
                                     no shutdown'''.format(tun1)))
            print(sr.r1.configure('''interface {}
                                     no shutdown'''.format(tun2)))
            i += 1
        # verfiy if tunnels are up after flapping tunnels
        tun_result = Verify.te_tunnels(sr.r1, 0,
                                       [sr.r1_r4_tunnel_list[random_tun_num],
                                        sr.r1_r5_tunnel_list[random_tun_num]])
        if tun_result == 1:
            self.debug = 1
            self.failed('tunnels did not come up')
        # 1. CLEAR COUNTERS
        Clear.counters(sr.uut_list)
        # 2. VERIFY FWD OVER TUNNEL
        result = Verify.route(sr.r1, [sr.r4_lo, sr.r5_lo],
                              [sr.r1_r4_tunnel_list[random_tun_num],
                               sr.r1_r5_tunnel_list[random_tun_num]])
        if result == 1:
            self.debug = 1
            self.failed('tunnel fwd was not as expected')
        # 3. SEND TRAFFIC
        ixia_result = Verify.ixia_traffic_rx()
        if ixia_result == 1:
            self.debug = 1
            self.failed('traffic failed')
        # 4. VERIFY TRAFFIC STATS
        result = Verify.interface_counters(sr.r1.handle,
                                           [sr.r1_r4_tunnel_list[random_tun_num],
                                           sr.r1_r5_tunnel_list[random_tun_num]])
        if result == 1:
            self.debug = 1
            self.failed('interface traffic accounting failed')
    @aetest.cleanup
    def cleanup(self):
        """Testcase cleanup."""
        sr = common_setup()
        # COLLECT DEBUG LOGS
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])
class Remove_loopback(aetest.Testcase):
    """Verify SR while removing R4 and R5 loopback configs."""
    debug = 0
    @aetest.setup
    def setup(self):
        """Testcase setup."""
    @aetest.test
    def test(self):
        """Testcase execution."""
        sr = common_setup()
        attempts = 3
        i = 1
        while i <= attempts:
            print(sr.r4.configure('no interface loopback0'))
            print(sr.r5.configure('no interface loopback0'))
            time.sleep(60)
            sr.r4.execute('rollback config last 1')
            sr.r5.execute('rollback config last 1')
            time.sleep(60)
            # verify route is over tunnel
            result = Verify.route(sr.r1, [sr.r4_lo, sr.r5_lo],
                                  [sr.r1_r4_tunnel_list[random_tun_num],
                                   sr.r1_r5_tunnel_list[random_tun_num]])
            if result == 1:
                self.debug = 1
                self.failed('tunnel fwd was not as expected')
            # verify l2vpn is up
            l2vpn_result = Verify.l2vpn(sr.r1, [sr.r4_lo, sr.r5_lo])
            if l2vpn_result != 0:
                self.debug = 1
                self.failed('l2vpn verify failed on {}'.format(sr.r1))
            i += 1
            # 1. CLEAR COUNTERS
            Clear.counters(sr.uut_list)
            # 2. SEND TRAFFIC
            ixia_result = Verify.ixia_traffic_rx()
            if ixia_result == 1:
                self.debug = 1
                self.failed('traffic failed')
            # 3. VERIFY TRAFFIC STATS
            result = Verify.interface_counters(sr.r1.handle,
                                               [sr.r1_r4_tunnel_list[random_tun_num],
                                               sr.r1_r5_tunnel_list[random_tun_num]])
            if result == 1:
                self.debug = 1
                self.failed('interface traffic accounting failed')
    @aetest.cleanup
    def cleanup(self):
        """Testcase cleanup."""
        sr = common_setup()
        # COLLECT DEBUG LOGS
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])
class Remove_l2vpn_config(aetest.Testcase):
    """Verify SR while adding and remving L2VPN config."""
    debug = 0
    @aetest.setup
    def setup(self):
        """Testcase setup."""
    @aetest.test
    def test(self):
        """Testcase execution."""
        sr = common_setup()
        # remove loopbacks from rtr4 and rtr5
        attempts = 10
        i = 1
        while i <= attempts:
            log.info(banner('removing l2vpn config attempt {}'.format(i)))
            print(sr.r1.configure('no l2vpn'))
            print(sr.r1.execute('''rollback config last 1'''))
            i += 1
        # verify l2vpn is up
        l2vpn_result = Verify.l2vpn(sr.r1, [sr.r4_lo, sr.r5_lo])
        if l2vpn_result != 0:
            self.debug = 1
            self.failed('l2vpn verify failed on {}'.format(sr.r1))
        # verify igp is up
        isis_result = Verify.routing_protocol(sr.r1, 3,
                                              protocol=proto)
        if isis_result != 0:
            self.debug = 1
            self.failed('isis verify failed on {}'.format(sr.r1))
        # verify tunnel is up
        tun_result = Verify.te_tunnels(sr.r1, 0,
                                       [sr.r1_r4_tunnel_list[random_tun_num],
                                        sr.r1_r5_tunnel_list[random_tun_num]])
        if tun_result == 1:
            self.debug = 1
            self.failed('tunnels did not come up')
        # 1. CLEAR COUNTERS
        Clear.counters(sr.uut_list)
        # 2. SEND TRAFFIC
        ixia_result = Verify.ixia_traffic_rx()
        if ixia_result == 1:
            self.debug = 1
            self.failed('traffic failed')
        # 3. VERIFY TRAFFIC STATS
        result = Verify.interface_counters(sr.r1.handle,
                                           [sr.r1_r4_tunnel_list[random_tun_num],
                                           sr.r1_r5_tunnel_list[random_tun_num]])
        if result == 1:
            self.debug = 1
            self.failed('interface traffic accounting failed')
    @aetest.cleanup
    def cleanup(self):
        """Testcase cleanup."""
        sr = common_setup()
        # COLLECT DEBUG LOGS
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])
class Remove_igp_config(aetest.Testcase):
    """Verify SR while adding and removing the IGP config."""
    debug = 0
    @aetest.setup
    def setup(self):
        """Testcase setup."""
    @aetest.test
    def test(self):
        """Testcase execution."""
        sr = common_setup()
        attempts = 5
        i = 1
        while i <= attempts:
            log.info(banner('removing igp config attempt {}'.format(i)))
            sr.r1.configure('no router {} 1'.format(proto))
            sr.r1.execute('''rollback config last 1''')
            i += 1
        time.sleep(30)
        # verify l2vpn is up
        l2vpn_result = Verify.l2vpn(sr.r1, [sr.r4_lo, sr.r5_lo])
        if l2vpn_result != 0:
            self.debug = 1
            self.failed('l2vpn verify failed on {}'.format(sr.r1))
        # verify igp is up
        isis_result = Verify.routing_protocol(sr.r1, 3,
                                              protocol=proto)
        if isis_result != 0:
            self.debug = 1
            self.failed('isis verify failed on {}'.format(sr.r1))
        # verify tunnel is up
        tun_result = Verify.te_tunnels(sr.r1, 0,
                                       [sr.r1_r4_tunnel_list[random_tun_num],
                                        sr.r1_r5_tunnel_list[random_tun_num]])
        if tun_result == 1:
            self.debug = 1
            self.failed('tunnels did not come up')
        # 1. CLEAR COUNTERS
        Clear.counters(sr.uut_list)
        # 2. SEND TRAFFIC
        ixia_result = Verify.ixia_traffic_rx()
        if ixia_result == 1:
            self.debug = 1
            self.failed('traffic failed')
        # 3. VERIFY TRAFFIC STATS
        result = Verify.interface_counters(sr.r1.handle,
                                           [sr.r1_r4_tunnel_list[random_tun_num],
                                           sr.r1_r5_tunnel_list[random_tun_num]])
        if result == 1:
            self.debug = 1
            self.failed('interface traffic accounting failed')
    @aetest.cleanup
    def cleanup(self):
        """Testcase cleanup."""
        sr = common_setup()
        # COLLECT DEBUG LOGS
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])
class Main_intf_flaps(aetest.Testcase):
    """Verify SR and flap the main interface."""
    debug = 0
    @aetest.setup
    def setup(self):
        """Testcase setup."""
        # remove random tunnel numbering as it could select a tunnel that
        # is configured for explicit path. For the following test cases you
        # will need to use dynamic tunnels
        sr = common_setup()
        # removing aa from tun 146 and 156. adding aa to random selected tunnel
        autoroute_announce(sr.r1,
                           [sr.r1_r4_tunnel_list[random_tun_num],
                            sr.r1_r5_tunnel_list[random_tun_num]],
                           [sr.r1_r4_tunnel_list[dynamic_tun_num],
                            sr.r1_r5_tunnel_list[dynamic_tun_num]])
        # getting tunnel id
        tun1_id = re.search(r'(\d+)', sr.r1_r4_tunnel_list[dynamic_tun_num])
        tun1_id_tt = 'tt' + tun1_id.group(0)
        tun2_id = re.search(r'(\d+)', sr.r1_r5_tunnel_list[dynamic_tun_num])
        tun2_id_tt = 'tt' + tun2_id.group(0)
        global tty_list
        global tun_nums
        tty_list = [tun1_id_tt, tun2_id_tt]
        tun_nums = [tun1_id.group(0), tun2_id.group(0)]
        i = 0
        for intfs in sr.r1_all_intfs:
            # shut down all interfaces except loopback and main intf
            if intfs == 'loopback0' or i == 0:
                print('intfs = {} i = {}'.format(intfs, i))
                i += 1
                continue
            else:
                print(sr.r1.configure('interface {} shutdown'.format(intfs)))
            i += 1
    @aetest.test
    def test(self):
        """Testcase execution."""
        sr = common_setup()
        # verify igp has 1 adj / neighbor
        isis_result = Verify.routing_protocol(sr.r1, 1,
                                              protocol=proto)
        if isis_result != 0:
            self.debug = 1
            self.failed('isis verify failed on {}'.format(sr.r1))
        # get igp interface
        klist = tcl.q.eval('router_show -device {} '
                           '-cmd show isis adjacency '
                           '-os_type xr '.format(sr.r1.handle))
        igp_intf = klist.adjacencies['1'].intf
        i = 0
        for tun in tty_list:
            # verify tunnels fwd is over main interface
            klist = tcl.q.eval('router_show -device {} '
                               '-cmd show mpls forwarding tunnels {} detail '
                               '-os_type xr '.format(sr.r1.handle,
                                                     tun_nums[i]))
            #mpls_te_intf = klist.tunid[tun].intf <---proc needs to get updated
            mpls_te_intf = klist.tunid[tun].prefix
            if igp_intf == mpls_te_intf:
                log.info('''pass expected tunnel fwd over interface {}
                            and got {}'''.format(igp_intf, mpls_te_intf))
            else:
                self.debug = 1
                self.failed('''fail expected tunnel fwd over interface {}
                            and got {}'''.format(igp_intf, mpls_te_intf))
            i += 1
        # flapping main interface
        i = 1
        while i <= 3:
            log.info(banner('''interface flap of {} attempt {}
                            '''.format(sr.r1_all_intfs[0], i)))
            sr.r1.configure('''interface {}
                            shutdown'''.format(sr.r1_all_intfs[0]))
            time.sleep(30)
            sr.r1.configure('''interface {}
                            no shutdown'''.format(sr.r1_all_intfs[0]))
            time.sleep(5)
            # verify igp is up after interface flap
            isis_result = Verify.routing_protocol(sr.r1, 1,
                                                  protocol=proto)
            if isis_result != 0:
                self.debug = 1
                self.failed('isis verify failed on {}'.format(sr.r1))
            # verify tunnel is up
            tun_result = Verify.te_tunnels(sr.r1, 0,
                                           [sr.r1_r4_tunnel_list[dynamic_tun_num],
                                            sr.r1_r5_tunnel_list[dynamic_tun_num]])
            if tun_result == 1:
                self.debug = 1
                self.failed('tunnels did not come up')
            # 1. CLEAR COUNTERS
            Clear.counters(sr.uut_list)
            # 2. SEND TRAFFIC
            ixia_result = Verify.ixia_traffic_rx()
            if ixia_result == 1:
                self.debug = 1
                self.failed('traffic failed')
            # 3. VERIFY TRAFFIC STATS
            result = Verify.interface_counters(sr.r1.handle,
                                               [sr.r1_r4_tunnel_list[dynamic_tun_num],
                                               sr.r1_r5_tunnel_list[dynamic_tun_num]])
            if result == 1:
                self.debug = 1
                self.failed('interface traffic accounting failed')
            i += 1
    @aetest.cleanup
    def cleanup(self):
        """Testcase cleanup."""
        sr = common_setup()
        # COLLECT DEBUG LOGS
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])
class Bundle_intf_flaps(aetest.Testcase):
    """Verify SR and flap the logical bundle interface."""
    debug = 0
    @aetest.setup
    def setup(self):
        """Testcase setup."""
    @aetest.test
    def test(self):
        """Testcase execution."""
        sr = common_setup()
        # unshut bundle
        sr.r1.configure('''interface {}
                        no shutdown'''.format(sr.r1_all_intfs[3]))
        time.sleep(10)
        # shut main interface
        sr.r1.configure('''interface {} shutdown'''.format(sr.r1_all_intfs[0]))
        # verify igp has 1 adj / neighbor
        igp_result = Verify.routing_protocol(sr.r1, 1,
                                             protocol=proto)
        if igp_result != 0:
            self.debug = 1
            self.failed('igp verify failed on {}'.format(sr.r1))
        # get igp interface
        if proto == 'ospf':
            klist = tcl.q.eval('router_show -device {} '
                               '-cmd show ospf neighbor '
                               '-os_type xr '.format(sr.r1.handle))
            ospf_intf = klist.interface_list
            if ospf_intf == 'bundle-ether12':
                igp_intf = 'be12'
        else:
            klist = tcl.q.eval('router_show -device {} '
                               '-cmd show isis adjacency '
                               '-os_type xr '.format(sr.r1.handle))
            igp_intf = klist.adjacencies['1'].intf
        i = 0
        for tun in tty_list:
            # verify tunnels fwd is over main interface
            klist = tcl.q.eval('router_show -device {} '
                               '-cmd show mpls forwarding tunnels {} detail '
                               '-os_type xr '.format(sr.r1.handle,
                                                     tun_nums[i]))
            mpls_te_intf = klist.tunid[tun].prefix
            if igp_intf == mpls_te_intf:
                log.info('''pass expected tunnel fwd over interface {}
                            and got {}'''.format(igp_intf, mpls_te_intf))
            else:
                self.debug = 1
                self.failed('''fail expected tunnel fwd over interface {}
                            and got {}'''.format(igp_intf, mpls_te_intf))
            i += 1
        # flapping bundle interface
        i = 1
        while i <= 3:
            log.info(banner('''interface flap of {} attempt {}
                            '''.format(sr.r1_all_intfs[3], i)))
            sr.r1.configure('''interface {}
                            shutdown'''.format(sr.r1_all_intfs[3]))
            time.sleep(30)
            sr.r1.configure('''interface {}
                            no shutdown'''.format(sr.r1_all_intfs[3]))
            time.sleep(5)
            # verify igp is up after interface flap
            isis_result = Verify.routing_protocol(sr.r1, 1,
                                                  protocol=proto)
            if isis_result != 0:
                self.debug = 1
                self.failed('isis verify failed on {}'.format(sr.uut_list[3]))
            # verify tunnel is up
            tun_result = Verify.te_tunnels(sr.r1, 0,
                                           [sr.r1_r4_tunnel_list[dynamic_tun_num],
                                            sr.r1_r5_tunnel_list[dynamic_tun_num]])
            if tun_result == 1:
                self.debug = 1
                self.failed('tunnels did not come up')
            # 1. CLEAR COUNTERS
            Clear.counters(sr.uut_list)
            # 2. SEND TRAFFIC
            ixia_result = Verify.ixia_traffic_rx()
            if ixia_result == 1:
                self.debug = 1
                self.failed('traffic failed')
            # 3. VERIFY TRAFFIC STATS
            result = Verify.interface_counters(sr.r1.handle,
                                               [sr.r1_r4_tunnel_list[dynamic_tun_num],
                                               sr.r1_r5_tunnel_list[dynamic_tun_num]])
            if result == 1:
                self.debug = 1
                self.failed('interface traffic accounting failed')
            i += 1
    @aetest.cleanup
    def cleanup(self):
        """Testcase cleanup."""
        sr = common_setup()
        # COLLECT DEBUG LOGS
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])
class Bundle_member_flaps(aetest.Testcase):
    """Verify SR over bundle, and flap bundle interface members."""
    debug = 0
    @aetest.setup
    def setup(self):
        """Testcase setup."""
    @aetest.test
    def test(self):
        """Testcase execution."""
        sr = common_setup()
        # shuting down bundle members
        i = 1
        for intfs in sr.r1_r2_intfs[1:3]:
            print('i = {}'.format(i))
            log.info(banner('''for BE12 shutting down intf {}
                            '''.format(intfs)))
            sr.r1.configure('interface {} shutdown'.format(intfs))
            print(sr.r1.execute('show interface bundle-ether12'.format(intfs)))
            time.sleep(5)
            if i == 2:
                # no need to check traffic stats once all bundle members are
                # shutdown as igp will go down as well.
                continue
            else:
                # 1. CLEAR COUNTERS
                Clear.counters(sr.uut_list)
                # 2. SEND TRAFFIC
                ixia_result = Verify.ixia_traffic_rx()
                if ixia_result == 1:
                    self.debug = 1
                    self.failed('traffic failed')
                # 3. VERIFY TRAFFIC STATS
                result = Verify.interface_counters(sr.r1.handle,
                                                   [sr.r1_r4_tunnel_list[dynamic_tun_num],
                                                   sr.r1_r5_tunnel_list[dynamic_tun_num]])
                if result == 1:
                    self.debug = 1
                    self.failed('interface traffic accounting failed')
            i += 1
        i = 1
        # brining bundle members back up with no shut
        for intfs in reversed(sr.r1_r2_intfs[1:3]):
            log.info(banner('''for BE12 brining intf {} back up with no shut
                            '''.format(intfs)))
            sr.r1.configure('''interface {}
                          no shutdown'''.format(intfs))
            # verify control plane is up
            if i == 1:
                # check if igp is up
                isis_result = Verify.routing_protocol(sr.r1, 1,
                                                      protocol=proto)
                if isis_result != 0:
                    self.debug = 1
                    self.failed('isis verify failed on {}'.format(sr.r1))
                # check if l2vpn is up
                l2vpn_result = Verify.l2vpn(sr.r1, [sr.r4_lo, sr.r5_lo])
                if l2vpn_result != 0:
                    self.debug = 1
                    self.failed('l2vpn verify failed on {}'.format(sr.r1))
                # check if tunnels are up
                tun_result = Verify.te_tunnels(sr.r1, 0,
                                               [sr.r1_r4_tunnel_list[dynamic_tun_num],
                                                sr.r1_r5_tunnel_list[dynamic_tun_num]])
                if tun_result == 1:
                    self.fdebug = 1
                    self.failed('tunnels did not come up')
            # 1. CLEAR COUNTERS
            Clear.counters(sr.uut_list)
            # 2. SEND TRAFFIC
            ixia_result = Verify.ixia_traffic_rx()
            if ixia_result == 1:
                self.debug = 1
                self.failed('traffic failed')
            # 3. VERIFY TRAFFIC STATS
            result = Verify.interface_counters(sr.r1.handle,
                                               [sr.r1_r4_tunnel_list[dynamic_tun_num],
                                               sr.r1_r5_tunnel_list[dynamic_tun_num]])
            if result == 1:
                self.debug = 1
                self.failed('interface traffic accounting failed')
            i += 1
    @aetest.cleanup
    def cleanup(self):
        """Testcase cleanup."""
        sr = common_setup()
        # COLLECT DEBUG LOGS
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])
class Bundle_add_remove_members(aetest.Testcase):
    """Verify SR over bundle, and add and remove bundle members."""
    debug = 0
    @aetest.setup
    def setup(self):
        """Testcase setup."""
    @aetest.test
    def test(self):
        """Testcase execution."""
        sr = common_setup()
        # removing bundle members
        i = 1
        for intfs in sr.r1_r2_intfs[1:3]:
            log.info(banner('''for BE12 removing intf {} '''.format(intfs)))
            sr.r1.configure('''interface {}
                            no bundle id'''.format(intfs))
            print(sr.r1.execute('show interface bundle-ether12'.format(intfs)))
            time.sleep(5)
            if i == 2:
                # no need to check traffic stats once all bundle members are
                # removed as igp will go down as well.
                time.sleep(30)
                continue
            else:
                # 1. CLEAR COUNTERS
                Clear.counters(sr.uut_list)
                # 2. SEND TRAFFIC
                ixia_result = Verify.ixia_traffic_rx()
                if ixia_result == 1:
                    self.debug = 1
                    self.failed('traffic failed')
                # 3. VERIFY TRAFFIC STATS
                result = Verify.interface_counters(sr.r1.handle,
                                                   [sr.r1_r4_tunnel_list[dynamic_tun_num],
                                                   sr.r1_r5_tunnel_list[dynamic_tun_num]])
                if result == 1:
                    self.debug = 1
                    self.failed('interface traffic accounting failed')
            i += 1
        i = 1
        # brining bundle members back up with no shut
        for intfs in reversed(sr.r1_r2_intfs[1:3]):
            log.info(banner('''for BE12 adding interface {} back to bundle
                            '''.format(intfs)))
            sr.r1.configure('''interface {}
                            bundle id 12 mode active'''.format(intfs))
            time.sleep(5)
            print(sr.r1.execute('show interface bundle-ether12'.format(intfs)))
            # verify control plane is up
            if i == 1:
                # check if igp is up
                isis_result = Verify.routing_protocol(sr.r1, 1,
                                                      protocol=proto)
                if isis_result != 0:
                    self.debug = 1
                    self.failed('isis verify failed on {}'.format(sr.r1))
                # check if l2vpn is up
                l2vpn_result = Verify.l2vpn(sr.r1, [sr.r4_lo, sr.r5_lo])
                if l2vpn_result != 0:
                    self.debug = 1
                    self.failed('l2vpn verify failed on {}'.format(sr.r1))
                # check if tunnels are up
                tun_result = Verify.te_tunnels(sr.r1, 0,
                                               [sr.r1_r4_tunnel_list[dynamic_tun_num],
                                                sr.r1_r5_tunnel_list[dynamic_tun_num]])
                if tun_result == 1:
                    self.debug = 1
                    self.failed('tunnels did not come up')
            # 1. CLEAR COUNTERS
            Clear.counters(sr.uut_list)
            # 2. SEND TRAFFIC
            ixia_result = Verify.ixia_traffic_rx()
            if ixia_result == 1:
                self.debug = 1
                self.failed('traffic failed')
            # 3. VERIFY TRAFFIC STATS
            result = Verify.interface_counters(sr.r1.handle,
                                               [sr.r1_r4_tunnel_list[dynamic_tun_num],
                                               sr.r1_r5_tunnel_list[dynamic_tun_num]])
            if result == 1:
                self.debug = 1
                self.failed('interface traffic accounting failed')
            i += 1
    @aetest.cleanup
    def cleanup(self):
        """Testcase cleanup."""
        sr = common_setup()
        # COLLECT DEBUG LOGS
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])
class Ti_lfa_path_switch(aetest.Testcase):
    """Verify basic traffic using adjacency sid via the bundle interface."""
    debug = 0
    @aetest.setup
    def setup(self):
        """Testcase setup."""
    @aetest.test
    def test(self):
        """Testcase execution."""
        sr = common_setup()
        i = 1
        while i <= 2:
            log.info(banner('path switching attempt {}'.format(i)))
            # bring up link between r1 and r5
            sr.r1.configure('''interface {}
                            no shutdown'''.format(sr.r1_r5_intfs[0]))
            time.sleep(5)
            # verify two paths in igp one to r1 to r2 and another from r1 to r5
            isis_result = Verify.routing_protocol(sr.r1, 2,
                                                  protocol=proto)
            if isis_result != 0:
                self.debug = 1
                self.failed('isis verify failed on {}'.format(sr.r1))
            # shutdown primary path which is multihop via r1 to r2
            sr.r1.configure('''interface {}
                            shutdown'''.format(sr.rtr1_rtr2_cfg_intf_list[1]))
            time.sleep(2)
            # verify now igp has only 1 via r1 to r5
            isis_result = Verify.routing_protocol(sr.r1, 1,
                                                  protocol=proto)
            if isis_result != 0:
                self.debug = 1
                self.failed('isis verify failed on {}'.format(sr.r1))
            # 1. CLEAR COUNTERS
            Clear.counters(sr.uut_list)
            # 2. SEND TRAFFIC
            ixia_result = Verify.ixia_traffic_rx()
            if ixia_result == 1:
                self.debug = 1
                self.failed('traffic failed')
            # 3. VERIFY TRAFFIC STATS
            result = Verify.interface_counters(sr.r1.handle,
                                               [sr.r1_r4_tunnel_list[dynamic_tun_num],
                                               sr.r1_r5_tunnel_list[dynamic_tun_num]])
            if result == 1:
                self.debug = 1
                self.failed('interface traffic accounting failed')
            # bring up multihop path r1 to r2
            sr.r1.config('''interface {}
                            no shutdown'''.format(sr.rtr1_rtr2_cfg_intf_list[1]))
            time.sleep(5)
            # verify two paths in igp one to r1 to r2 and another from r1 to r5
            isis_result = Verify.routing_protocol(sr.r1, 2,
                                                  protocol=proto)
            if isis_result != 0:
                self.debug = 1
                self.failed('isis verify failed on {}'.format(sr.r1))
            # shutdown path via r1 to r5 so fwd gose over r1 to r2 multihop path
            sr.r1.configure('''interface {}
                           shutdown'''.format(sr.r1_r5_intfs[0]))
            time.sleep(5)
            # verify igp has only one path r1 to r2
            isis_result = Verify.routing_protocol(sr.r1, 1,
                                                  protocol=proto)
            if isis_result != 0:
                self.debug = 1
                self.failed('isis verify failed on {}'.format(sr.r1))
            # 1. CLEAR COUNTERS
            Clear.counters(sr.uut_list)
            # 2. SEND TRAFFIC
            ixia_result = Verify.ixia_traffic_rx()
            if ixia_result == 1:
                self.debug = 1
                self.failed('traffic failed')
            # 3. VERIFY TRAFFIC STATS
            result = Verify.interface_counters(sr.r1.handle,
                                               [sr.r1_r4_tunnel_list[dynamic_tun_num],
                                               sr.r1_r5_tunnel_list[dynamic_tun_num]])
            if result == 1:
                self.debug = 1
                self.failed('interface traffic accounting failed')
            i += 1
    @aetest.cleanup
    def cleanup(self):
        """Testcase cleanup."""
        sr = common_setup()
        # COLLECT DEBUG LOGS
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])
class Prefered_path(aetest.Testcase):
    """Verify SR with prefered path config."""
    debug = 0
    @aetest.setup
    def setup(self):
        """Testcase setup."""
        sr = common_setup()
        # bring up all the physical paths
        for intfs in sr.rtr1_rtr2_cfg_intf_list:
            print(sr.r1.configure('''interface {}
                                     no shutdown'''.format(intfs)))
        for intfs in sr.r1_r2_intfs:
            print(sr.r1.configure('''interface {}
                                     no shutdown'''.format(intfs)))
        # add autoroute announce to all tunnels
        for r1_r5_tun, r1_r4_tun in itertools.zip_longest(sr.r1_r5_tunnel_list,
                                                          sr.r1_r4_tunnel_list):
            sr.r1.configure('''interface {}
                            autoroute announce'''.format(r1_r5_tun))
            sr.r1.configure('''interface {}
                            autoroute announce'''.format(r1_r4_tun))
        # add prefered path config to l2vpn
        nbr_ip = [sr.r4_lo, sr.r5_lo]
        tuns = ['142', '152']
        pref_path_config = ''
        my_class = 1
        i = 0
        for ip in nbr_ip:
            klist = tcl.q.eval('::xr::config::l2vpn '
                                    '-port_list {} '
                                    '-switching_mode bridge-group '
                                    '-pw_class my_pref_path_{} '
                                    '-bridge_domain_count 1 '
                                    '-neighbor_list {} '
                                    '-split_horizon '
                                    '-prefer_path_tun_id {} '
                                    '-bridge_group_name sr_vpls '
                                    '-interfaces_per_bd 1 '
                                    '-neighbors_per_domain 1 '
                                    '-pw_start 1 '
                                    '-encap mpls '.format(tclstr(sr.r1_tgen_intfs),
                                                    my_class, tclstr(ip),
                                                    tuns[i]))
            pref_path_config += klist.config_str
            my_class += 1
            i += 1
            sr.r1.configure(pref_path_config)
        # verify all igp paths are up
        igp_result = Verify.routing_protocol(sr.r1, 3,
                                              protocol=proto)
        l2vpn_result = Verify.l2vpn(sr.r1, [sr.r4_lo, sr.r5_lo])
        time.sleep(60)
        config = sr.r1.execute('show run l2vpn')
        if 'preferred-path interface tunnel-te' not in config:
            self.failed('preferred-path CLI not found in config')
        if igp_result != 0:
            self.debug = 1
            self.failed('igp verify failed on {}'.format(sr.r1))
        if l2vpn_result != 0:
            self.debug = 1
            self.failed('l2vpn verify failed on {}'.format(sr.r1))
    @aetest.test
    def test(self):
        """Testcase execution."""
        sr = common_setup()
        # 1. CLEAR COUNTERS
        Clear.counters(sr.uut_list)
        # 2. SEND TRAFFIC
        ixia_result = Verify.ixia_traffic_rx()
        if ixia_result == 1:
            self.debug = 1
            self.failed('traffic failed')
        # 3. VERIFY TRAFFIC STATS
        result = Verify.interface_counters(sr.r1.handle,
                                           [sr.r1_r4_tunnel_list[1],
                                           sr.r1_r5_tunnel_list[1]])
        if result == 1:
            self.debug = 1
            self.failed('interface traffic accounting failed')
    @aetest.cleanup
    def cleanup(self):
        """Testcase cleanup."""
        sr = common_setup()
        # COLLECT DEBUG LOGS
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])
class Change_prefered_path_tunnel_config(aetest.Testcase):
    """Verify an place modification of the prefered path tunnel config."""
    debug = 0
    @aetest.setup
    def setup(self):
        """Testcase setup."""
        sr = common_setup()
        sr.r1.configure('''l2vpn
                         pw-class my_pref_path_1
                          encapsulation mpls
                           preferred-path interface tunnel-te 143
                          !
                         !
                         pw-class my_pref_path_2
                          encapsulation mpls
                           preferred-path interface tunnel-te 153''')
        config = sr.r1.execute('show run l2vpn')
        if ('preferred-path interface tunnel-te 143' in config and
                'preferred-path interface tunnel-te 153' in config):
                log.info('preferred-path config changed as expected')
        else:
            self.failed('preferred-path config did not change as expexted')
        # verify all igp paths are up
        igp_result = Verify.routing_protocol(sr.r1, 3,
                                              protocol=proto)
        l2vpn_result = Verify.l2vpn(sr.r1, [sr.r4_lo, sr.r5_lo])
        if igp_result != 0:
            self.debug = 1
            self.failed('igp verify failed on {}'.format(sr.r1))
        if l2vpn_result != 0:
            self.debug = 1
            self.failed('l2vpn verify failed on {}'.format(sr.r1))
        time.sleep(60)
    @aetest.test
    def test(self):
        """Testcase execution."""
        sr = common_setup()
        # 1. CLEAR COUNTERS
        Clear.counters(sr.uut_list)
        # 2. SEND TRAFFIC
        ixia_result = Verify.ixia_traffic_rx()
        if ixia_result == 1:
            self.debug = 1
            self.failed('traffic failed')
        # 3. VERIFY TRAFFIC STATS
        result = Verify.interface_counters(sr.r1.handle,
                                           [sr.r1_r4_tunnel_list[2],
                                           sr.r1_r5_tunnel_list[2]])
        if result == 1:
            self.debug = 1
            self.failed('interface traffic accounting failed')
    @aetest.cleanup
    def cleanup(self):
        """Testcase cleanup."""
        sr = common_setup()
        # COLLECT DEBUG LOGS
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])
class Prefered_path_with_flow_label(aetest.Testcase):
    """Verify SR traffic using flow label and traffic ecmp is over the physical
    path.
    """
    debug = 0
    @aetest.setup
    def setup(self):
        """Testcase setup."""
        sr = common_setup()
        sr.r1.configure('''l2vpn
                         load-balancing flow src-dst-ip
                         pw-class my_pref_path_1
                          encapsulation mpls
                          load-balancing
                           flow-label both
                           preferred-path interface tunnel-te 143
                          !
                         !
                         pw-class my_pref_path_2
                          encapsulation mpls
                          load-balancing
                           flow-label both
                           preferred-path interface tunnel-te 153''')
        config = sr.r1.execute('show run l2vpn')
        if ('load-balancing flow src-dst-ip' in config and
                'flow-label both' in config):
                log.info('preferred-path and flow lable config found in CLI')
        else:
            self.failed('preferred-path and flow lable config '
                        'not found in CLI')
        # verify all igp paths are up
        igp_result = Verify.routing_protocol(sr.r1, 3,
                                              protocol=proto)
        l2vpn_result = Verify.l2vpn(sr.r1, [sr.r4_lo, sr.r5_lo])
        if igp_result != 0:
            self.debug = 1
            self.failed('igp verify failed on {}'.format(sr.r1))
        if l2vpn_result != 0:
            self.debug = 1
            self.failed('l2vpn verify failed on {}'.format(sr.r1))
        time.sleep(60)
    @aetest.test
    def test(self):
        """Testcase execution."""
        sr = common_setup()
        # 1. CLEAR COUNTERS
        Clear.counters(sr.uut_list)
        # 2. SEND TRAFFIC
        ixia_result = Verify.ixia_traffic_rx()
        if ixia_result == 1:
            self.debug = 1
            self.failed('traffic failed')
        # 3. VERIFY TRAFFIC STATS
        result = Verify.interface_counters(sr.r1.handle,
                                           [sr.r1_r4_tunnel_list[2],
                                           sr.r1_r5_tunnel_list[2]])
        if result == 1:
            self.debug = 1
            self.failed('interface traffic accounting failed')
    @aetest.cleanup
    def cleanup(self):
        """Testcase cleanup."""
        sr = common_setup()
        # COLLECT DEBUG LOGS
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])
class Control_word(aetest.Testcase):
    """Verify SR using control word."""
    debug = 0
    @aetest.setup
    def setup(self):
        """Testcase setup."""
        sr = common_setup()
        rtr1_config_str = ''
        rtr4_config_str = ''
        rtr5_config_str = ''
        # REMOVE AA FROM ALL TUNNELS
        for r1_r5_tun, r1_r4_tun in itertools.zip_longest(sr.r1_r5_tunnel_list,
                                                         sr.r1_r4_tunnel_list):
            sr.r1.configure('''interface {}
                            no autoroute announce'''.format(r1_r5_tun))
            sr.r1.configure('''interface {}
                            no autoroute announce'''.format(r1_r4_tun))
        # ADD AA BACK TO SINGLE TUNNEL
        sr.r1.configure('''interface {}
                        autoroute announce'''.format(sr.r1_r4_tunnel_list[1]))
        sr.r1.configure('''interface {}
                        autoroute announce'''.format(sr.r1_r5_tunnel_list[1]))
        # REMOVE L2VPN CONFIG
        for rtr in sr.uut_list:
            log.info('removing l2vpn config on {}'.format(rtr))
            sr.rtr.configure('no l2vpn')
        # ADD L2VPN CONFIG WITH CONTROL WORD
        for rtr in sr.uut_list:
            place_holder_cfg = ''
            if rtr == sr.r1:
                l2vpn_nbr_ip = [sr.r4_lo, sr.r5_lo]
                l2_vpn_intfs = [sr.r1_tgen_intfs]
            if rtr == sr.r4:
                l2vpn_nbr_ip = [sr.r1_lo, sr.r5_lo]
                l2_vpn_intfs = [sr.r4_tgen_intfs]
            if rtr == sr.r5:
                l2vpn_nbr_ip = [sr.r1_lo, sr.r4_lo]
                l2_vpn_intfs = [sr.r5_tgen_intfs]
            if rtr == sr.r1 or rtr == sr.r4 or rtr == sr.r5:
                for ip in l2vpn_nbr_ip:
                    klist = tcl.q.eval('::xr::config::l2vpn '
                                            '-port_list {} '
                                            '-switching_mode bridge-group '
                                            '-pw_class my_class '
                                            '-bridge_domain_count 1 '
                                            '-neighbor_list {} '
                                            '-split_horizon '
                                            '-control_word enable '
                                            '-bridge_group_name sr_vpls '
                                            '-interfaces_per_bd 1 '
                                            '-neighbors_per_domain 1 '
                                            '-pw_start 1 '
                                            '-encap mpls '.format(tclstr(l2_vpn_intfs),
                                                                 tclstr(ip)))
                    place_holder_cfg += klist.config_str
                    if rtr == sr.r1:
                        rtr1_config_str += place_holder_cfg
                    if rtr == sr.r4:
                        rtr4_config_str += place_holder_cfg
                    if rtr == sr.r5:
                        rtr5_config_str += place_holder_cfg
        sr.r1.configure(rtr1_config_str)
        sr.r4.configure(rtr4_config_str)
        sr.r5.configure(rtr5_config_str)
        # VERIFY CONTROL WORD IS ENABLED
        i = 1
        for nbr in [sr.r4_lo, sr.r5_lo]:
            while i <= 5:
                out = sr.r1.execute('show l2vpn bridge-domain '
                                    'neighbor {} detail'.format(nbr))
                if 'Control word enabled                        enabled' in out:
                    log.info('pass control word is enabled for '
                           'nbr {}'.format(nbr))
                    break
                elif i == 5:
                    self.debug = 1
                    self.failed('fail control word is not enabled for '
                           'nbr {}'.format(nbr))
                else:
                    log.info('still polling for nbr {}'.format(nbr))
                time.sleep(60)
                i += 1
    @aetest.test
    def test(self):
        """Testcase execution."""
        sr = common_setup()
        # 1. CLEAR COUNTERS
        Clear.counters(sr.uut_list)
        # 2. SEND TRAFFIC
        ixia_result = Verify.ixia_traffic_rx()
        if ixia_result == 1:
            self.debug = 1
            self.failed('traffic failed')
        # 3. VERIFY TRAFFIC STATS
        result = Verify.interface_counters(sr.r1.handle,
                                           [sr.r1_r4_tunnel_list[1],
                                           sr.r1_r5_tunnel_list[1]])
        if result == 1:
            self.debug = 1
            self.failed('interface traffic accounting failed')
    @aetest.cleanup
    def cleanup(self):
        """Testcase cleanup."""
        sr = common_setup()
        # COLLECT DEBUG LOGS
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])
class common_cleanup(aetest.CommonCleanup):
    """Common Cleanup for Sample Test."""
    sr = common_setup()
    @aetest.subsection
    def post_router_check(self, uut_list=sr.uut_list):
        #tcl.q.eval('post_router_check {} '.format(uut_list[0].handle))
        pass
    @aetest.subsection
    def unconfig(self, uut_list=sr.uut_list):
        """ Common Cleanup subsection. """
        ###########################
        # POST ROUTER CLEAN UP
        ###########################
        for rtr in uut_list:
            log.info('CLEANUP ON RTR {}'.format(rtr))
            tcl.q.eval('::xr::unconfig::router '
                       '-device {} '
                       '-load_file {}'.format(rtr.handle,
                                              SrScriptArgs.startup_config))
if __name__ == '__main__':
    aetest.main()
