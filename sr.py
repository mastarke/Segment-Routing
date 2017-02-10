#!/bin/env python

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

def ixia_srv6_segments_list_args(segment_list, num=13):
    '''used to create ixia srv6 args that are passed to ixia traffic_config in
       order to make segments list in the traffic stream'''
    num = num
    count = len(segment_list)
    ixia_segment_list_arg = []
    for i in range(count):
        arg = 'ipv6RoutingType4.segmentRoutingHeader.segmentList.ipv6SID-{}'.format(num)
        ixia_segment_list_arg.append(arg)

        num += 1

    return ixia_segment_list_arg

def dec_to_hex(d):
    """Convert to hex."""
    d = d
    output = hex(d).split('x')[1]
    len(output)

    return output

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

    def ixia_traffic_rx(stream_hld, ixia_result=0, packet_tolerance=5.000,
                        wait_time=60):
        # GETTING COMMON SETUP INSTANCE ATTRIBUTES
        sr = Common_setup(wait_time)

        # RUN IXIA TRAFFIC
        sr.ixia.traffic_control(action='run',
                                port_handle=sr.port_handle_list,
                                handle=stream_hld)
        time.sleep(wait_time)

        if sr.vpls_flag == True:
            unicast_streams = stream_list[0:2]
        else:
            unicast_streams = stream_list

        # VERIFY UNICAST TRAFFIC STREAMS
        for streams_ids in unicast_streams:
            traffic_status = sr.ixia.traffic_stats(mode='stream ',
                                                streams='{} '.format(streams_ids))
            if sr.vpls_flag == True:
                # GET TX PKTS
                tx_pkts = traffic_status[sr.port_handle_list[0]].stream\
                [streams_ids].tx.total_pkts
                # GET EXPECTED PACKETS
                exp_pkts = traffic_status[sr.port_handle_list[0]].stream\
                [streams_ids].rx.expected_pkts
                # GET PACKET LOSS
                pkt_loss = traffic_status[sr.port_handle_list[0]].stream\
                [streams_ids].rx.loss_percent
            else:
                # GET TX PKTS
                tx_pkts = traffic_status[sr.port_handle_list[0]].stream\
                [streams_ids].tx.total_pkts
                # GET EXPECTED PACKETS
                exp_pkts = traffic_status[sr.port_handle_list[2]].stream\
                [streams_ids].rx.expected_pkts
                # GET PACKET LOSS
                pkt_loss = traffic_status[sr.port_handle_list[2]].stream\
                [streams_ids].rx.loss_percent

            if float(pkt_loss) >= packet_tolerance:
                log.error('''fail stream {} tx_pkts {} exp_pkts {} pkt loss percent {}'''
                     .format(streams_ids, tx_pkts, exp_pkts, pkt_loss))

                ixia_result = 1
            else:
                log.info('''pass stream {} tx_pkts {} exp_pkts {} pkt loss percent {}'''
                     .format(streams_ids, tx_pkts, exp_pkts, pkt_loss))

        if sr.vpls_flag == True:
            # VERIFY MCAST TRAFFIC STREAMS
            for streams_ids in stream_list[2:5]:

                traffic_status = sr.ixia.traffic_stats(mode='stream ',
                                                    streams='{} '.format(streams_ids))

                tx_pkts = traffic_status[sr.port_handle_list[0]].stream[streams_ids].tx.total_pkts
                exp_pkts_p1 = traffic_status[sr.port_handle_list[1]].stream[streams_ids].rx.expected_pkts
                exp_pkts_p2 = traffic_status[sr.port_handle_list[2]].stream[streams_ids].rx.expected_pkts
                pkt_loss_p1 = traffic_status[sr.port_handle_list[1]].stream[streams_ids].rx.loss_percent
                pkt_loss_p2 = traffic_status[sr.port_handle_list[2]].stream[streams_ids].rx.loss_percent

                if float(pkt_loss_p1) and float(pkt_loss_p2) >= packet_tolerance:

                    log.error('''fail for stream id {} tx pkts sent on {} = {} rx pkts on
                            {} = {} loss percent {} rx pkts on {} = {} loss percent {}
                            '''.format(streams_ids, sr.port_handle_list[0], tx_pkts,
                                       sr.port_handle_list[1], exp_pkts_p1,
                                       pkt_loss_p1, sr.port_handle_list[2],
                                       exp_pkts_p2, pkt_loss_p2))
                    ixia_result = 1
                else:
                    log.info('''pass for stream id {} tx pkts sent on {} = {} rx pkts on
                            {} = {} loss percent {} rx pkts on {} = {} loss percent {}
                            '''.format(streams_ids, sr.port_handle_list[0], tx_pkts,
                                       sr.port_handle_list[1], exp_pkts_p1,
                                       pkt_loss_p1, sr.port_handle_list[2],
                                       exp_pkts_p2, pkt_loss_p2))

        return ixia_result

    def srv6_show_cef_pd_check(rtr, lc, pd_flag='on', prefix='192:168:1::1',
                               result=0):
        for i in range(3):
            output = rtr.execute('show cef ipv6 {} hardware '
                                   'egress detail location {}'.format(prefix,
                                                                     lc))
            print(output)
            if pd_flag == 'on':
                # CHECKING IF PD FLAG IS ON
                if 'local_ipv6_sid: 1' in output:
                    log.info('Pass...found srv6 PD flag enabled')
                    break
                elif i == 2:
                    result = 1
                    log.error('Fail...srv6 PD flag is not enabled')
                else:
                    log.info('Polling for srv6 PD flag')
            else:
                # CHECKING IF PD FLAG IS OFF
                if 'local_ipv6_sid: 1' not in output:
                    log.info('Pass...srv6 PD flag has been removed successful')
                    break
                elif i == 2:
                    result = 1
                    log.error('Fail...srv6 PD flag is not removed.')
                else:
                    log.info('Polling srv6 PD flag')


            time.sleep(20)

        return result

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

class Common_setup(aetest.CommonSetup):
    """Setup up common setup"""

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
    r1_lov6 = '192:168:1::1'
    r2_lo = '192.168.2.1'
    r2_lov6 = '192:168:2::1'
    r3_lo = '192.168.3.1'
    r3_lov6 = '192:168:3::1'
    r4_lo = '192.168.4.1'
    r4_lov6 = '192:168:4::1'
    r5_lo = '192.168.5.1'
    r5_lov6 = '192:168:5::1'
    af_list = ['ipv4', 'ipv6']

    global proto
    proto = SrScriptArgs.routing_proto
    global dynamic_tun_num
    # selecting random number for tunnel
    dynamic_tun_num = random.randint(0, 1)
    # selecting random tunnel
    global random_tun_num
    random_tun_num = random.randint(0, 5)


    # OPTINAL FLAG ARGUMENTS PROVIDED VIA JOB FILE
    # SETTING VPLS_FLAG
    try:
        vpls_flag = SrScriptArgs.vpls_flag
    except:
        log.info('Setting vpls_flag to None')
        vpls_flag = None

    # SETTING TE_FLAG
    try:
        te_flag = SrScriptArgs.te_flag
    except:
        log.info('setting te_flag to None')
        te_flag = None

    # SETTING SRV6_FLAG
    try:
        srv6_flag = SrScriptArgs.srv6_flag
    except:
        log.info('Setting srv6_flag to None')
        srv6_flag = None

    # SETTING EXPECTED NUMBER OF ISIS ADJACENCY
    if srv6_flag == True:
        exp_isis_prx = 6
        pfx = 2
        adj = str(2)
    else:
        exp_isis_prx = 3
        pfx = 1
        adj = str(1)

    # R1 TO R5 EXPLICIT PATH LIST TO R5 PRIMARY PATH
    r1_r5_exp_path1_lo0 = [r2_lo, r3_lo, r4_lo, r5_lo]
    r5_r1_exp_path1_lo0 = [r4_lo, r3_lo, r2_lo, r1_lo]
    r1_r5_exp_path2_main = ['12.1.1.2', '23.1.1.2', '34.1.1.2', '45.1.1.2']
    r1_r5_exp_path3_sub = ['12.1.2.2', '23.1.1.2', '34.1.1.2', '45.1.1.2']
    r1_r5_exp_path4_be = ['12.1.3.2', '23.1.1.2', '34.1.1.2', '45.1.1.2']
    r1_r5_exp_path_list = [r1_r5_exp_path1_lo0, r1_r5_exp_path2_main,
                           r1_r5_exp_path3_sub, r1_r5_exp_path4_be]

    # R5 TO R1 EXPLIST PATH LIST
    r5_list = copy.deepcopy(r1_r5_exp_path_list)
    r5_r1_exp_path_list = ip_add_convert(r5_list, ip_digit='1')

    r5_r1_exp_path_list = make_sub_list(r5_r1_exp_path_list, 4)
    for item in r5_r1_exp_path_list:
        item.reverse()

    r5_r1_exp_path_list.insert(0, r5_r1_exp_path1_lo0)

    # R1 EXPLICIT PATH LIST TO R4, REMOVE LAST ITEM OF LIST
    r1_r4_exp_path_list = copy.deepcopy(r1_r5_exp_path_list)
    for item in r1_r4_exp_path_list:
        del item[3]

    # R4 TO R1 EXPLICIT PATH LIST
    r4_r1_exp_path_list = copy.deepcopy(r5_r1_exp_path_list)
    for item in r4_r1_exp_path_list:
        del item[0]

    # R1 TO R5 = R5_R1_EXP_PATH_LIST, R5 TO R1 = R5_R1_EXP_PATH_LIST
    # R1 TO R4 = R1_R4_EXP_PATH_LIST, R4 TO R1 = R4_R1_EXP_PATH_LIST

    # R1 TO R5 BACKUP PATHS
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
                edge_ipv4 = '101.1.1.1'
                edge_ipv6 = '101::1'

            if rtr == r4:
                intfs = r4_tgen_intfs
                edge_ipv4 = '104.1.1.1'
                edge_ipv6 = '104::1'

            if rtr == r5:
                intfs = r5_tgen_intfs
                edge_ipv4 = '105.1.1.1'
                edge_ipv6 = '105::1'

            try:
                if vpls_flag == True:
                    # CONFIG MAIN INTF FOR L2 TRANSPORT
                    returnList = tcl.q.eval('::xr::config::ether '
                                            '-l2transport 1 '
                                            '-port_list {} '
                                            '-mask 24 '.format(tclstr(intfs)))

                    place_holder_cfg += returnList.config_str
                else:
                    # ADD IPV4 ADDRESS
                    returnList = tcl.q.eval('::xr::config::ether '
                                            '-port_list {} '
                                            '-mask 24 '
                                            '-ip_addr_list {} '.format(
                                                                    tclstr(intfs),
                                                                    edge_ipv4))

                    place_holder_cfg += returnList.config_str

                    # ADD IPV6 ADDRESS
                    returnList = tcl.q.eval('::xr::config::ether '
                                            '-port_list {} '
                                            '-mask 64 '
                                            '-ip_addr_list {} '.format(
                                                                    tclstr(intfs),
                                                                    edge_ipv6))
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
            except:
                log.error('ENSURE VPLS_FLAG IS SET TO: Ture or False')
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
                ip_addr_list_v6.append('12:{}::1'.format(ip))
                ip += 1

        if rtr == r2:
            num_intfs = len(r2_r1_intfs)
            intfs = r2_r1_intfs
            ip = 1
            for i in range(num_intfs):
                ip_addr_list.append('12.1.{}.2'.format(ip))
                ip_addr_list_v6.append('12:{}::2'.format(ip))
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

            # ADD IPV6 ADDRESS
            returnList = tcl.q.eval('::xr::config::ether '
                                    '-port_list {} '
                                    '-mask 64 '
                                    '-ip_addr_list {} '.format(tclstr(intfs[0]),
                                                               tclstr(ip_addr_list_v6[0])))
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

            # ADD IPV6 ADDRESS
            returnList = tcl.q.eval('::xr::config::ether '
                                    '-port_list {} '
                                    '-ip_addr_list {} '
                                    '-auto_negotiate 1 '
                                    '-mask 64 '
                                    '-transceiver_all 1 '
                                    '-efp_outer_encap_type dot1q '
                                    '-vlan_start_num 101 '
                                    '-subintf_start_num 101 '
                                    '-subintf_count 1 '
                                    '-vlan_mode efp '
                                    '-efp_outer_tag_type '
                                    'vlan-id'.format(tclstr(intfs[0]),
                                                     tclstr(ip_addr_list_v6[1])))

            # APPEND TO CONFIG STR
            if rtr == r1:
                rtr1_config_str += returnList.config_str
            if rtr == r2:
                rtr2_config_str += returnList.config_str
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

            # APPEND INTERFACE TO CONFIG STRING
            # APPEND CONFIG TO CONFIG_STR
            if rtr == r1:
                rtr1_config_str += returnList.config_str
                rtr1_rtr2_cfg_intf_list.append(returnList.bundle_intfs)
            if rtr == r2:
                rtr2_config_str += returnList.config_str
                rtr2_rtr1_cfg_intf_list.append(returnList.bundle_intfs)

            # ADD IPV6 ADDRESS
            returnList = tcl.q.eval('::xr::config::link_bundle '
                                    '-bundle_id 12 '
                                    '-bundle_count 1 '
                                    '-intf_per_bundle 2 '
                                    '-bundle_mode active '
                                    '-ip_addr_list {} '
                                    '-protocol ipv6 '
                                    '-ip_mask_list 64 '
                                    '-intf_list {} '.format(
                                     tclstr(ip_addr_list_v6[2]), tclstr(intfs[1:3])))

            # APPEND CONFIG STRING
            if rtr == r1:
                rtr1_config_str += returnList.config_str
            if rtr == r2:
                rtr2_config_str += returnList.config_str
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
                ip_addr_list_v6.append('15:{}::1'.format(ip))
                ip += 1

        elif rtr == r5:
            num_intfs = len(r5_r1_intfs)
            intfs = r5_r1_intfs
            ip = 1
            for i in range(num_intfs):
                ip_addr_list.append('15.1.{}.2'.format(ip))
                ip_addr_list_v6.append('15:{}::2'.format(ip))
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

            # ADD IPV6 ADDRESS
            returnList = tcl.q.eval('::xr::config::ether '
                                    '-port_list {} '
                                    '-mask 64 '
                                    '-ip_addr_list {} '.format(tclstr(intfs[0]),
                                                               tclstr(ip_addr_list_v6[0])))
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

            # CONFIG IPV6 BUNDLE INTERFACE RTR1 TO RTR5
            returnList = tcl.q.eval('::xr::config::link_bundle '
                                    '-bundle_id 15 '
                                    '-bundle_count 1 '
                                    '-intf_per_bundle 2 '
                                    '-bundle_mode active '
                                    '-ip_addr_list {} '
                                    '-protocol ipv6 '
                                    '-ip_mask_list 64 '
                                    '-intf_list {} '.format(
                                     tclstr(ip_addr_list_v6[1]),
                                     tclstr(intfs[1:3])))

            # GETTING LIST OF BUNDLE INTERFACES
            if rtr == r1:
                rtr1_config_str += returnList.config_str
            if rtr == r5:
                rtr5_config_str += returnList.config_str
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

            # ADDING IPV6 ADDRESS
            returnList = tcl.q.eval('::xr::config::ether '
                                    '-port_list {} '
                                    '-mask 64 '
                                    '-ip_addr_list {} '.format(
                                     tclstr(intfs_1[0]), tclstr(ip_addr_list_1_v6[0])))

            place_holder_cfg += returnList.config_str

            # ADDING IPV6 ADDRESS
            returnList = tcl.q.eval('::xr::config::ether '
                                    '-port_list {} '
                                    '-mask 64 '
                                    '-ip_addr_list {} '.format(
                                     tclstr(intfs_2[0]), tclstr(ip_addr_list_2_v6[0])))

            place_holder_cfg += returnList.config_str
        else:

            # ADDING IPV4 ADDRESS
            returnList = tcl.q.eval('::xr::config::ether '
                                    '-port_list {} '
                                    '-ip_addr_list {} '.format(
                                     tclstr(intfs_1[0]), tclstr(ip_addr_list_1[0])))

            place_holder_cfg += returnList.config_str

            # ADDING IPV6 ADDRESS
            returnList = tcl.q.eval('::xr::config::ether '
                                    '-port_list {} '
                                    '-mask 64 '
                                    '-ip_addr_list {} '.format(
                                     tclstr(intfs_1[0]), tclstr(ip_addr_list_1_v6[0])))

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
    prefix_sid_ipv4 = 101
    prefix_sid_ipv6 = 1001
    for rtr in uut_list:
        intfs = []
        place_holder_cfg = ''

        if rtr == r1:
            intfs = r1_all_intfs + r1_tgen_intfs
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
            intfs = r5_all_intfs + r5_tgen_intfs
            l2vpn_nbr_ip = [r1_lo, r4_lo]
            l2_vpn_intfs = [r5_tgen_intfs]

        # CONFIG LOOPBACK INTERFACES0
        if srv6_flag == True:
            looback_intf = '''
                           interface loopback0
                           ip address 192.168.{i}.1/32
                           ipv6 address 192:168:{i}::1/128 segment-routing
                           ipv6-sr prefix-sid
                           root'''.format(i=i)
        else:
            looback_intf = '''
                           interface loopback0
                           ip address 192.168.{i}.1/32
                           ipv6 address 192:168:{i}::1/128
                           root'''.format(i=i)

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
            for af in af_list:
                if af == 'ipv4':
                    # ADDING ISIS CONFIG FOR IPV4 ADDRESS FAMILY
                    prefix_sid = prefix_sid_ipv4
                    returnList = tcl.q.eval('::xr::config::isis '
                                            '-process_name 1 '
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
                                            '-intf_prefix_sid  {ps} '
                                            '-mpls_te_rtr_id 192.168.{i}.1 '
                                            '-mpls_ldp_auto_config 1 '
                                            '-mpls_te_level 2-only '
                                            '-bfd_fast disable '
                                            '-is_type level-2-only '
                                            '-af_type {af} '.format(i=i,
                                                                    ps=prefix_sid,
                                                                    intfs=tclstr(intfs),
                                                                    af=af))
                else:
                    # ADDING ISIS CONFIG FOR IPV6 ADDRESS FAMILY
                    prefix_sid = prefix_sid_ipv6
                    returnList = tcl.q.eval('::xr::config::isis '
                                            '-process_name 1 '
                                            '-nsf cisco '
                                            '-net_id 49.001.192.168.00{i}.001.00 '
                                            '-network_type point-to-point '
                                            '-intf_list {intfs} '
                                            '-mtr_level 2 '
                                            '-sr_mpls_sr_prefer 1 '
                                            '-sr_prefix_sid_map_rx 1 '
                                            '-sr_prefix_sid_map_adv_local  1 '
                                            '-intf_prefix_sid_flag 1 '
                                            '-intf_prefix_sid  {ps} '
                                            '-bfd_fast disable '
                                            '-af_type {af} '.format(i=i,
                                                                    ps=prefix_sid,
                                                                    intfs=tclstr(intfs),
                                                                    af=af))
                prefix_sid_ipv4 += 1
                prefix_sid_ipv6 += 1
                place_holder_cfg += returnList.config_str

        ##########################################
        # CONFIG BGP
        ##########################################
        try:
            if srv6_flag == True:
                bgp_config = ''
                if rtr == r1:
                    bgp_nbr = r5_lov6
                if rtr == r5:
                    bgp_nbr = r1_lov6

                # ADD IBGP BETWEEN R1 AND R5
                if rtr == r1 or rtr == r5:
                    bgp_config = '''
                                 route-policy pass-all
                                 pass
                                 exit
                                 !
                                 router bgp 100
                                 address-family ipv6 unicast
                                 !
                                 neighbor {nbr}
                                  remote-as 100
                                  update-source Loopback0
                                  address-family ipv6 unicast
                                  root
                             '''.format(nbr=bgp_nbr)

                place_holder_cfg += bgp_config

                # ADD EBGP CONFIG FROM R5 TO IXIA
                if rtr == r5:
                    bgp_config = '''
                                  router bgp 100
                                  neighbor 105::2
                                  remote-as 200
                                  address-family ipv6 unicast
                                   route-policy pass-all in
                                   route-policy pass-all out
                                   next-hop-self
                                   root
                                   !
                              '''
                place_holder_cfg += bgp_config
        except:
            log.info('srv6_flag not set skipping bgp setup')

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

        try:
            if vpls_flag == True:
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
        except:
            log.info('SKIPING L2VPN BRIDGE CONFIG AS vpls_flag IS NOT SET'
                     'TO EITHER True or False')

        try:
            if te_flag == True:
                ###############################
                # CONFIG SR TUNNELS
                ###############################
                if rtr == r1:

                    # R1 TO R5 DYNAMIC + EXPLICIT PRIMARY TUNNELS
                    sr_cfg = config_sr_tunnels(tun_dst=r5_lo, tunnel_id=151,
                                               num_dynamic_tuns=2,
                                               exp_list_names=exp_names,
                                               exp_ip_list=r1_r5_exp_path_list)

                    place_holder_cfg += sr_cfg

                    # R1 TO R4 DYNAMIC + EXPLICIT PRIMARY TUNNELS
                    sr_cfg = config_sr_tunnels(tun_dst=r4_lo, tunnel_id=141,
                                               num_dynamic_tuns=2,
                                               exp_list_names=exp_names,
                                               exp_ip_list=r1_r4_exp_path_list)

                    place_holder_cfg += sr_cfg

                    # CREATING LIST OF TUNNELS
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

                    # R4 TO R1 DYNAMIC + EXPLICIT PRIMARY TUNNELS
                    sr_cfg = config_sr_tunnels(tun_dst=r1_lo, tunnel_id=141,
                                               num_dynamic_tuns=2,
                                               exp_list_names=exp_names,
                                               exp_ip_list=r4_r1_exp_path_list)

                    place_holder_cfg += sr_cfg

                if rtr == r5:
                    # R5 TO R1 DYNAMIC + EXPLICIT PRIMARY TUNNELS
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

            else:
                # CONFIG WITHOUT TUNNELS
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
        except:
            log.info('Ensure that te_flag is set to either True or False')


    # CREATE LIST OF ALL ROUTER CONFIG_STR
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
    try:
        if vpls_flag == True:
            # CONFIGURING IXIA TGEN INTERFACE FOR RTR1 VPLS SCENARIO
            tgen_r1_port1 = ixia.interface_config(port_handle=tgen_port_handle1,
                                                  phy_mode='fiber',
                                                  intf_ip_addr='21.1.1.1',
                                                  speed=SrScriptArgs.r1_tgen1_speed,
                                                  gateway='21.1.1.5')

            tgen_r1_port1 = tgen_r1_port1.interface_handle

            # CONFIGURING IXIA TGEN INTERFACE FOR RTR4 VPLS SCENARIO
            tgen_r4_port1 = ixia.interface_config(port_handle=tgen_port_handle2,
                                                  phy_mode='fiber',
                                                  intf_ip_addr='21.1.1.4',
                                                  speed=SrScriptArgs.r4_tgen1_speed,
                                                  gateway='21.1.1.1')

            tgen_r4_port1 = tgen_r4_port1.interface_handle

            # CONFIGURING IXIA TGEN INTERFACE FOR RTR5 VPLS SCENARIO
            tgen_r5_port1 = ixia.interface_config(port_handle=tgen_port_handle3,
                                                  phy_mode='fiber',
                                                  intf_ip_addr='21.1.1.5',
                                                  speed=SrScriptArgs.r5_tgen1_speed,
                                                  gateway='21.1.1.1')

            tgen_r5_port1 = tgen_r5_port1.interface_handle
        else:
            # CONFIGURING IXIA TGEN INTERFACE FOR RTR1
            tgen_r1_port1 = ixia.interface_config(port_handle=tgen_port_handle1,
                                                  intf_ip_addr='101.1.1.2',
                                                  gateway='101.1.1.1',
                                                  ipv6_intf_addr='101::2',
                                                  ipv6_gateway='101::1',
                                                  speed=SrScriptArgs.r1_tgen1_speed,
                                                  phy_mode='fiber')

            tgen_r1_port1 = tgen_r1_port1.interface_handle

            # CONFIGURING IXIA TGEN INTERFACE FOR RTR4
            tgen_r4_port1 = ixia.interface_config(port_handle=tgen_port_handle2,
                                                  intf_ip_addr='104.1.1.2',
                                                  gateway='104.1.1.1',
                                                  ipv6_intf_addr='104::2',
                                                  ipv6_gateway='104::1',
                                                  speed=SrScriptArgs.r4_tgen1_speed,
                                                  phy_mode='fiber')

            tgen_r4_port1 = tgen_r4_port1.interface_handle

            # CONFIGURING IXIA TGEN INTERFACE FOR RTR5
            tgen_r5_port1 = ixia.interface_config(port_handle=tgen_port_handle3,
                                                  intf_ip_addr='105.1.1.2',
                                                  gateway='105.1.1.1',
                                                  ipv6_intf_addr='105::2',
                                                  ipv6_gateway='105::1',
                                                  speed=SrScriptArgs.r5_tgen1_speed,
                                                  phy_mode='fiber')

            tgen_r5_port1 = tgen_r5_port1.interface_handle
    except:
        log.error('Ensure vpls_flag is set to: True or False')


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
        try:
            if vpls_flag == True:
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
        except:
            log.info('SKIPING L2VPN CHECKS AS VPLS FLAG IS NOT SET TO TRUE')

        #######################################
        # VERIFY TE-TUNNEL'S ARE UP
        #######################################
        try:
            if te_flag == True:
                for rtr in uut_list:
                    if rtr == self.r1 or rtr == self.r4 or rtr == self.r5:
                        te_result = Verify.te_tunnels(rtr=rtr)

                    if te_result != 0:
                        self.failed('''failed to bring up tunnels
                                       or rtr {}'''.format(rtr))
        except:
            log.info('SKIPING TUNNEL CHECKS AS TE FLAG IS NOT SET TO TRUE')

    @aetest.subsection
    def verify_ixia(self):

        # GETTING DMAC ADRESS OF EDGE INTERFACES
        global stream_list
        #############################################
        # CONFIG IXIA TRAFFIC STREAM
        ############################################
        try:
            if self.vpls_flag == True:
                # STREAM R1 TO R5 AND R5 BACK TO R1
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
                # STREAM R1 TO R4 AND R4 BACK TO R1
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

                # MCAST TRAFFIC UNKOWN SRC AND DST MAC
                s3 = self.ixia.traffic_config(mode='create',
                                              traffic_generator='ixnetwork_540',
                                              convert_to_raw='1',
                                              name='r1_mcast_traffic',
                                              ip_src_addr='1.1.1.1',
                                              ip_src_mode='increment',
                                              ip_src_count='1000',
                                              ip_src_step='0.0.0.1',
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
                                              rate_pps=5000)
                s3_id = s3.stream_id

                # BCAST TRAFFIC DST MAC AS FFFF.FFFF.FFFF
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

                # UNKOWN UNICAST TRAFFIC KNOWN SRC MAC AND UNKOWN DST MAC
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
                stream_list = [s1_id, s2_id, s3_id, s4_id, s5_id]
            else:
                # REMOVING ISIS POINT-TO-POINT INTERFACE TYPE ON R1 TO TGEN LINK
                self.r1.configure('''router isis 1
                                     interface {}
                                     no point-to-point'''.format(
                                                tclstr(self.r1_tgen_intfs)))

                # REMOVING ISIS POINT-TO-POINT INTERFACE TYPE ON R5 TO TGEN LINK
                self.r5.configure('''router isis 1
                                     interface {}
                                     no point-to-point'''.format(
                                                tclstr(self.r5_tgen_intfs)))
                # 1. CREATE ISIS EMULATION ON RTR1
                klist = self.ixia.emulation_isis_config(
                                                mode='create',
                                                reset='yes',
                                                port_handle=self.tgen_port_handle1,
                                                ip_version='4_6',
                                                multi_topology='1',
                                                area_id='490001',
                                                system_id='000000000001',
                                                count='1',
                                                interface_handle=self.tgen_r1_port1,
                                                intf_metric='10',
                                                wide_metrics='1',
                                                routing_level='L2')

                r1_isis_handle = klist.handle

                # 1A. CREATE ROUTE RANGE FOR ISIS EMULATION
                klist = self.ixia.emulation_isis_topology_route_config(
                                                mode='create',
                                                type='external',
                                                handle=r1_isis_handle,
                                                ip_version='4_6',
                                                external_ip_start='100.1.1.0',
                                                external_ip_pfx_len='30',
                                                external_ip_step='0.0.0.1',
                                                external_count='1',
                                                external_route_count='1',
                                                external_metric='10',
                                                external_ipv6_start='1000::1',
                                                external_ipv6_pfx_len='64',
                                                external_ipv6_step='0:0:0:1:0:0:0:0')

                r1_emulation_hdl_v4 = klist.elem_handle['4']
                r1_emulation_hdl_v6 = klist.elem_handle['6']


                # 1. CREATE ISIS EMULATION ON RTR5
                klist = self.ixia.emulation_isis_config(
                                                mode='create',
                                                reset='yes',
                                                port_handle=self.tgen_port_handle3,
                                                ip_version='4_6',
                                                multi_topology='1',
                                                area_id='490001',
                                                system_id='000000000005',
                                                count='1',
                                                interface_handle=self.tgen_r5_port1,
                                                intf_metric='10',
                                                wide_metrics='1',
                                                routing_level='L2')

                r5_isis_handle = klist.handle

                # CREATE ROUTE RANGE FOR ISIS EMULATION
                klist = self.ixia.emulation_isis_topology_route_config(
                                                mode='create',
                                                type='external',
                                                handle=r5_isis_handle,
                                                ip_version='4_6',
                                                external_ip_start='200.1.1.0',
                                                external_ip_pfx_len='30',
                                                external_ip_step='0.0.0.1',
                                                external_count='1',
                                                external_route_count='1',
                                                external_metric='10',
                                                external_ipv6_start='2000::1',
                                                external_ipv6_pfx_len='64',
                                                external_ipv6_step='0:0:0:1:0:0:0:0')

                r5_emulation_hdl_v4 = klist.elem_handle['4']
                r5_emulation_hdl_v6 = klist.elem_handle['6']

                # CREATE BGP EMULATION
                klist = self.ixia.emulation_bgp_config(mode='enable',
                                        port_handle=self.tgen_port_handle3,
                                        local_router_id='105.1.1.2',
                                        local_router_id_enable=1,
                                        hold_time=90,
                                        ipv4_unicast_nlri=1,
                                        ipv6_unicast_nlri=1,
                                        local_as=200,
                                        ip_version=6,
                                        interface_handle=self.tgen_r5_port1,
                                        remote_ip_addr='105.1.1.1',
                                        neighbor_type='external',
                                        netmask=30,
                                        local_ip_addr='105.1.1.2',
                                        update_interval=0)

                r5_bgp_emulation_hdl_v6 = klist.handles

                # CREATE BGP ROUTE RANGE
                klist = self.ixia.emulation_bgp_route_config(
                                       mode='add',
                                       handle=r5_bgp_emulation_hdl_v6,
                                       ip_version=6,
                                       prefix_step=1,
                                       prefix='2001::1',
                                       next_hop_set_mode='same',
                                       num_routes='1',
                                       originator_id='0.0.0.0',
                                       packing_to=0,
                                       prefix_to=64)

                r5_bgp_route_range = klist.bgp_routes

                # STEP 1. CREATE STREAM 1 SRV6
                s1 = self.ixia.traffic_config(mode='create',
                                            traffic_generator='ixnetwork_540',
                                            convert_to_raw='1',
                                            endpointset_count=1,
                                            ipv6_src_addr='100::1',
                                            ipv6_dst_addr='192:168:1::1',
                                            emulation_src_handle=r1_emulation_hdl_v6,
                                            emulation_dst_handle=r5_emulation_hdl_v6,
                                            src_dest_mesh='one_to_one',
                                            route_mesh='one_to_one',
                                            hosts_per_net='1',
                                            name='SRv6_R1_to_R5_with_SRH',
                                            merge_destinations='1',
                                            circuit_endpoint_type='ipv6',
                                            rate_pps='5000',
                                            frame_size='400',
                                            length_mode='fixed',
                                            tx_mode='advanced',
                                            transmit_mode='single_burst',
                                            pkts_per_burst='100000',
                                            l3_protocol='ipv6',
                                            ipv6_flow_label='5000',
                                            ipv6_flow_label_mode='incr',
                                            ipv6_flow_label_count='50',
                                            track_by='sourceDestEndpointPair0')

                s1_id = s1.stream_id
                config_elements  = s1['traffic_item']

                # STEP 2. ADD TYPE 4 ROUTING HEADER
                s1 = self.ixia.traffic_config(
                        mode = 'modify_or_insert' ,
                        stream_id = config_elements,
                        stack_index = 3,
                        pt_handle = 'ipv6RoutingType4')

                last_stack = s1['last_stack']

                segment_list = ['2000::1', '192:168:5::1', '192:168:4::1',
                                '192:168:3::1', '192:168:2::1', '192:168:1::1']

                # STEP 3. CALLING FUNCTION TO CREATE IXIA ARGUMENT LIST
                ixia_srv6_arg = ixia_srv6_segments_list_args(segment_list)
                for arg1, arg2 in itertools.zip_longest(ixia_srv6_arg, segment_list):
                    # ADD TO SEGMENTS LIST
                    log.info('segment list = {} {}'.format(arg1,arg2))
                    s1 = self.ixia.traffic_config(mode = 'set_field_values',
                            header_handle= last_stack,
                            pt_handle= 'ipv6RoutingType4',
                            field_handle=arg1,
                            field_activeFieldChoice='0',
                            field_optionalEnabled='1',
                            field_fullMesh='0',
                            field_trackingEnabled='0',
                            field_valueType= 'singleValue',
                            field_singleValue=arg2,
                            field_auto='0')

                # STEP 4. SET SEGMENTS LEFT
                s1 = self.ixia.traffic_config(
                        mode = 'set_field_values',
                        header_handle = last_stack,
                        pt_handle =  'ipv6RoutingType4',
                        field_handle = 'ipv6RoutingType4.segmentRoutingHeader.segmentsLeft-4',
                        field_activeFieldChoice = '0',
                        field_auto = '0',
                        field_optionalEnabled = '1',
                        field_fullMesh = '0',
                        field_trackingEnabled = '0',
                        field_valueType =  'singleValue',
                        field_singleValue = '5')

                # STEP 1. CREATE STREAM 2 SRV6 Transiet
                s2 = self.ixia.traffic_config(mode='create',
                                            traffic_generator='ixnetwork_540',
                                            convert_to_raw='1',
                                            endpointset_count=1,
                                            ipv6_src_addr='100::1',
                                            ipv6_dst_addr='2000::1',
                                            emulation_src_handle=r1_emulation_hdl_v6,
                                            emulation_dst_handle=r5_emulation_hdl_v6,
                                            src_dest_mesh='one_to_one',
                                            route_mesh='one_to_one',
                                            hosts_per_net='1',
                                            name='SRv6_R1_to_R5_Transient',
                                            merge_destinations='1',
                                            circuit_endpoint_type='ipv6',
                                            rate_pps='5000',
                                            frame_size='400',
                                            length_mode='fixed',
                                            tx_mode='advanced',
                                            transmit_mode='single_burst',
                                            pkts_per_burst='100000',
                                            l3_protocol='ipv6',
                                            track_by='sourceDestEndpointPair0')

                s2_id = s2.stream_id
                config_elements  = s2['traffic_item']

                # STEP 2. ADD TYPE 4 ROUTING HEADER
                s2 = self.ixia.traffic_config(
                        mode = 'modify_or_insert' ,
                        stream_id = config_elements,
                        stack_index = 3,
                        pt_handle = 'ipv6RoutingType4')

                last_stack = s2['last_stack']

                segment_list = ['3000::1', '100:168:5::1', '100:168:4::1',
                                '100:168:3::1', '100:168:2::1', '100:168:1::1']

                # STEP 3. CALLING FUNCTION TO CREATE IXIA ARGUMENT LIST
                ixia_srv6_arg = ixia_srv6_segments_list_args(segment_list)
                for arg1, arg2 in itertools.zip_longest(ixia_srv6_arg, segment_list):
                    # ADD TO SEGMENTS LIST
                    log.info('segment list = {} {}'.format(arg1,arg2))
                    s2 = self.ixia.traffic_config(mode = 'set_field_values',
                            header_handle= last_stack,
                            pt_handle= 'ipv6RoutingType4',
                            field_handle=arg1,
                            field_activeFieldChoice='0',
                            field_optionalEnabled='1',
                            field_fullMesh='0',
                            field_trackingEnabled='0',
                            field_valueType= 'singleValue',
                            field_singleValue=arg2,
                            field_auto='0')

                # STEP 4. SET SEGMENTS LEFT
                s2 = self.ixia.traffic_config(
                        mode = 'set_field_values',
                        header_handle = last_stack,
                        pt_handle =  'ipv6RoutingType4',
                        field_handle = 'ipv6RoutingType4.segmentRoutingHeader.segmentsLeft-4',
                        field_activeFieldChoice = '0',
                        field_auto = '0',
                        field_optionalEnabled = '1',
                        field_fullMesh = '0',
                        field_trackingEnabled = '0',
                        field_valueType =  'singleValue',
                        field_singleValue = '5')

                # STEP 1. CREATE STREAM 3 SRV6 C-FLAG
                s3 = self.ixia.traffic_config(mode='create',
                                            traffic_generator='ixnetwork_540',
                                            convert_to_raw='1',
                                            endpointset_count=1,
                                            ipv6_src_addr='100::1',
                                            ipv6_dst_addr='192:168:1::1',
                                            emulation_src_handle=r1_emulation_hdl_v6,
                                            emulation_dst_handle=r5_emulation_hdl_v6,
                                            src_dest_mesh='one_to_one',
                                            route_mesh='one_to_one',
                                            hosts_per_net='1',
                                            name='SRv6_R1_to_R5_C_Flag',
                                            merge_destinations='1',
                                            circuit_endpoint_type='ipv6',
                                            rate_pps='5000',
                                            frame_size='400',
                                            length_mode='fixed',
                                            tx_mode='advanced',
                                            transmit_mode='single_burst',
                                            pkts_per_burst='100000',
                                            l3_protocol='ipv6',
                                            track_by='sourceDestEndpointPair0')

                s3_id = s3.stream_id
                config_elements  = s3['traffic_item']

                # STEP 2. ADD TYPE 4 ROUTING HEADER
                s3 = self.ixia.traffic_config(
                        mode = 'modify_or_insert' ,
                        stream_id = config_elements,
                        stack_index = 3,
                        pt_handle = 'ipv6RoutingType4')

                last_stack = s3['last_stack']

                # STEP 3. SET C FLAG TO CLEAN UP ON EGRESS
                s1 = self.ixia.traffic_config(
                        mode='set_field_values',
                        header_handle=last_stack,
                        pt_handle='ipv6RoutingType4',
                        field_handle="ipv6RoutingType4.segmentRoutingHeader.srhFlags.cFlag-6",
                        field_activeFieldChoice='0',
                        field_auto='0',
                        field_optionalEnabled='1',
                        field_fullMesh='1',
                        field_trackingEnabled='0',
                        field_valueType='singleValue',
                        field_singleValue='1')

                # LIST OF SEGMENTS
                segment_list = ['2000::1', '192:168:5::1', '192:168:4::1',
                                '192:168:3::1', '192:168:2::1', '192:168:1::1']

                # STEP 4. CALLING FUNCTION TO CREATE IXIA ARGUMENT LIST
                ixia_srv6_arg = ixia_srv6_segments_list_args(segment_list)
                for arg1, arg2 in itertools.zip_longest(ixia_srv6_arg, segment_list):
                    # ADD TO SEGMENTS LIST
                    log.info('segment list = {} {}'.format(arg1,arg2))
                    s3 = self.ixia.traffic_config(mode = 'set_field_values',
                            header_handle= last_stack,
                            pt_handle= 'ipv6RoutingType4',
                            field_handle=arg1,
                            field_activeFieldChoice='0',
                            field_optionalEnabled='1',
                            field_fullMesh='0',
                            field_trackingEnabled='0',
                            field_valueType= 'singleValue',
                            field_singleValue=arg2,
                            field_auto='0')

                # STEP 5. SET SEGMENTS LEFT
                s3 = self.ixia.traffic_config(
                        mode = 'set_field_values',
                        header_handle = last_stack,
                        pt_handle =  'ipv6RoutingType4',
                        field_handle = 'ipv6RoutingType4.segmentRoutingHeader.segmentsLeft-4',
                        field_activeFieldChoice = '0',
                        field_auto = '0',
                        field_optionalEnabled = '1',
                        field_fullMesh = '0',
                        field_trackingEnabled = '0',
                        field_valueType =  'singleValue',
                        field_singleValue = '5')

                # STEP 1. CREATE STREAM 4 SRV6 TO BGP ROUTE
                s4 = self.ixia.traffic_config(mode='create',
                                            traffic_generator='ixnetwork_540',
                                            convert_to_raw='1',
                                            endpointset_count=1,
                                            ipv6_src_addr='100::1',
                                            ipv6_dst_addr='192:168:1::1',
                                            emulation_src_handle=r1_emulation_hdl_v6,
                                            emulation_dst_handle=r5_bgp_route_range,
                                            src_dest_mesh='one_to_one',
                                            route_mesh='one_to_one',
                                            hosts_per_net='1',
                                            name='SRv6_R1_to_R5_SRH_BGP',
                                            merge_destinations='1',
                                            circuit_endpoint_type='ipv6',
                                            rate_pps='5000',
                                            frame_size='400',
                                            length_mode='fixed',
                                            tx_mode='advanced',
                                            transmit_mode='single_burst',
                                            pkts_per_burst='100000',
                                            l3_protocol='ipv6',
                                            track_by='sourceDestEndpointPair0')

                s4_id = s4.stream_id
                config_elements  = s4['traffic_item']

                # STEP 2. ADD TYPE 4 ROUTING HEADER
                s4 = self.ixia.traffic_config(
                        mode = 'modify_or_insert' ,
                        stream_id = config_elements,
                        stack_index = 3,
                        pt_handle = 'ipv6RoutingType4')

                last_stack = s4['last_stack']
                segment_list = ['2001::1', '192:168:5::1', '192:168:4::1',
                                '192:168:3::1', '192:168:2::1', '192:168:1::1']

                # STEP 3. CALLING FUNCTION TO CREATE IXIA ARGUMENT LIST
                ixia_srv6_arg = ixia_srv6_segments_list_args(segment_list)
                for arg1, arg2 in itertools.zip_longest(ixia_srv6_arg, segment_list):
                    # ADD TO SEGMENTS LIST
                    log.info('segment list = {} {}'.format(arg1,arg2))
                    s4 = self.ixia.traffic_config(mode = 'set_field_values',
                            header_handle= last_stack,
                            pt_handle= 'ipv6RoutingType4',
                            field_handle=arg1,
                            field_activeFieldChoice='0',
                            field_optionalEnabled='1',
                            field_fullMesh='0',
                            field_trackingEnabled='0',
                            field_valueType= 'singleValue',
                            field_singleValue=arg2,
                            field_auto='0')

                # STEP 4. SET SEGMENTS LEFT
                s4 = self.ixia.traffic_config(
                        mode = 'set_field_values',
                        header_handle = last_stack,
                        pt_handle =  'ipv6RoutingType4',
                        field_handle = 'ipv6RoutingType4.segmentRoutingHeader.segmentsLeft-4',
                        field_activeFieldChoice = '0',
                        field_auto = '0',
                        field_optionalEnabled = '1',
                        field_fullMesh = '0',
                        field_trackingEnabled = '0',
                        field_valueType =  'singleValue',
                        field_singleValue = '5')

                # STEP 1. CREATE STREAM 5 SRV6 TO BGP ROUTE 10 LABEL
                s5 = self.ixia.traffic_config(mode='create',
                                            traffic_generator='ixnetwork_540',
                                            convert_to_raw='1',
                                            endpointset_count=1,
                                            ipv6_src_addr='100::1',
                                            ipv6_dst_addr='192:168:1::1',
                                            emulation_src_handle=r1_emulation_hdl_v6,
                                            emulation_dst_handle=r5_bgp_route_range,
                                            src_dest_mesh='one_to_one',
                                            route_mesh='one_to_one',
                                            hosts_per_net='1',
                                            name='SRv6_R1_to_R5_SRH_10_label',
                                            merge_destinations='1',
                                            circuit_endpoint_type='ipv6',
                                            rate_pps='5000',
                                            frame_size='400',
                                            length_mode='fixed',
                                            tx_mode='advanced',
                                            transmit_mode='single_burst',
                                            pkts_per_burst='100000',
                                            l3_protocol='ipv6',
                                            track_by='sourceDestEndpointPair0')

                s5_id = s5.stream_id
                config_elements  = s5['traffic_item']

                # STEP 2. ADD TYPE 4 ROUTING HEADER
                s5 = self.ixia.traffic_config(
                        mode = 'modify_or_insert' ,
                        stream_id = config_elements,
                        stack_index = 3,
                        pt_handle = 'ipv6RoutingType4')

                last_stack = s5['last_stack']
                segment_list = ['2001::1', '192:168:5::1', '192:168:4::1',
                                '192:168:3::1', '192:168:2::1', '192:168:3::1',
                                '192:168:2::1', '192:168:3::1', '192:168:2::1',
                                '192:168:1::1']

                # STEP 3. CALLING FUNCTION TO CREATE IXIA ARGUMENT LIST
                ixia_srv6_arg = ixia_srv6_segments_list_args(segment_list)
                for arg1, arg2 in itertools.zip_longest(ixia_srv6_arg, segment_list):
                    # ADD TO SEGMENTS LIST
                    log.info('segment list = {} {}'.format(arg1,arg2))
                    s5 = self.ixia.traffic_config(mode = 'set_field_values',
                            header_handle= last_stack,
                            pt_handle= 'ipv6RoutingType4',
                            field_handle=arg1,
                            field_activeFieldChoice='0',
                            field_optionalEnabled='1',
                            field_fullMesh='0',
                            field_trackingEnabled='0',
                            field_valueType= 'singleValue',
                            field_singleValue=arg2,
                            field_auto='0')

                # STEP 4. SET SEGMENTS LEFT
                s5 = self.ixia.traffic_config(
                        mode = 'set_field_values',
                        header_handle = last_stack,
                        pt_handle =  'ipv6RoutingType4',
                        field_handle = 'ipv6RoutingType4.segmentRoutingHeader.segmentsLeft-4',
                        field_activeFieldChoice = '0',
                        field_auto = '0',
                        field_optionalEnabled = '1',
                        field_fullMesh = '0',
                        field_trackingEnabled = '0',
                        field_valueType =  'singleValue',
                        field_singleValue = '9')

                stream_list = [s1_id, s2_id, s3_id, s4_id, s5_id]

        except:
            log.error('Ensure vpls_flag is set to True or False')

        try:
            if self.srv6_flag == True:
                log.info(banner('STARTING IXIA EMULATIONS'))
                # START BGP EMULATION
                result = self.ixia.emulation_bgp_control(
                                                handle=r5_bgp_emulation_hdl_v6,
                                                mode='start')
                if result['status'] != '1':
                    self.failed('Ixia BGP emulation failed', goto = ['exit'])

                # START ISIS
                isis_hdl_ixia = [r5_isis_handle ,r1_isis_handle]
                ixia_p_hdl = [self.tgen_port_handle3, self.tgen_port_handle1]
                result = self.ixia.emulation_isis_control(mode='start',
                                                        handle=isis_hdl_ixia,
                                                        port_handle=ixia_p_hdl)

                if result['status'] != '1':
                    self.failed('Ixia ISIS emulation failed', goto = ['exit'])

                time.sleep(5)

                # VERIFY ISIS EMULATION IS UP
                for rtr in [self.r1, self.r5]:
                    if rtr == self.r1:
                        prefix = '2000::'
                    else:
                        prefix = '1000::'
                    for attempts in range(6):
                        cmd = rtr.execute('show cef ipv6 {}'.format(prefix))
                        log.info('### output from {} {}### '.format(rtr,
                                                                    prefix))
                        print(cmd)
                        if 'remote adjacency' in cmd:
                            log.info('pass found expected prefix')
                            break
                        elif attempts == 5:
                            self.failed('failed cound not find '
                            'the prefix {} attempts {}'.format(prefix,attempts),
                            goto = ['exit'])
                        else:
                            log.info('polling...prefix {} attempt {}'.format(rtr,
                                                                    attempts))
                            time.sleep(15)

                # VERIFY BGP EMULATION IS UP AND ROUTE LEARNED ON R1
                for i in range(5):
                    output = self.r1.execute('show route ipv6 bgp')
                    if 'B    2001::/64' in output:
                        log.info('Pass BGP route is learned on {}'.format(
                                                                     self.r1))
                        break
                    elif i == 4:
                        self.failed('Fail BGP route not learned on {}'.format(
                                                                      self.r1))
                    else:
                        log.info('polling if bgp ipv6 bgp '
                                 'route learned on {}'.format(self.r1))
                        time.sleep(15)

        except:
            log.info('Ensure srv6_flag is set to true')

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

        # GETTING LINECARD OF UUT
        global uut_lc
        uut_lc = tcl.eval('rtr_show_utils::intf_convert '
                          '-device {} '
                          '-intf {} '
                          '-return node_id '.format(self.r1.handle,
                                                    self.r1_tgen_intfs[0]))

#######################################################################
#                          TESTCASE BLOCK                             #
#######################################################################

class SanityTraffic(aetest.Testcase):
    """Verify SR sanity case."""

    debug = 0

    @aetest.setup
    def setup(self):
        """Testcase setup."""

    @aetest.test
    def verify_ping_trace_route(self):
        """Testcase execution to verify ping and trace route."""
        sr = Common_setup()

        # SHUTTING DOWN SHORTEST 1 HOP PATH VIA R1 AND R5 INTERFACES
        r1_r5_shut_intfs = []
        r1_r5_shut_intfs.append(sr.r1_all_intfs[1])
        r1_r5_shut_intfs.append(sr.r1_all_intfs[4])
        for intf in r1_r5_shut_intfs:
            sr.r1.configure('interface {} shutdown'.format(intf))

        for i in range(5):
            output = sr.r1.execute('ping {}'.format(sr.r5_lov6))
            if 'Success rate is 100 percent' in output:
                log.info('ping result was : Success rate is 100 percent')
                break
            elif i == 4:
                self.failed('Ping failed')
            else:
                log.info('retrying ping as result was not 100 percent '
                      'attempt number {}'.format(i))

        # TRACEROUTE TEST
        output = sr.r1.execute('traceroute ipv6 {}'.format(sr.r5_lov6))
        match = re.findall(r'Label \d+', output)
        hops = len(match)
        # VEIFY CORRECT NUMBER OF MPLS HOPS
        if hops != 3:
            self.failed('expected 3 MPLS hops and found only'.format(hops))

        # VERIFY LABES ARE WHAT IS TO BE EXPECTED
        count = 1
        for item in match:
            if '51010' in item and hops == 3:
                log.info('found SR label : {} for hop {}'.format(item,count))
            else:
                self.failed('incorrect label found {} expected 51010')
            count += 1

        # UNSHUT INTERFACES FROM R1 TO R5
        for intf in r1_r5_shut_intfs:
            sr.r1.configure('''interface {}
                            no shutdown'''.format(intf))

    @aetest.test
    def verify_rib_show_route(self):
        """Testcase execution to verify RIB."""
        sr = Common_setup()
        output = sr.r1.execute('show route ipv6 {} detail'.format(sr.r1_lov6))

        if 'ipv6 SR' not in output:
            self.failed('Fail could not find ipv6 SR in RIB')
        else:
            log.info('Pass ipv6 SR found in RIB')


    @aetest.test
    def verify_fib_show_cef(self):
        """Testcase execution to verify FIB."""
        sr = Common_setup()
        result = Verify.srv6_show_cef_pd_check(rtr=sr.r1, lc=uut_lc)
        if result == 1:
            self.failed('SRv6 PD check failed')

    @aetest.test
    def verify_traffic_streams(self):
        """Testcase execution to verify basic traffic."""
        sr = Common_setup()
        # START TRAFFIC
        ixia_result = Verify.ixia_traffic_rx(stream_list)

        # CLEAR COUNTERS
        Clear.counters(sr.uut_list)

    @aetest.test
    def verify_np_counters(self):
        """Verify NP counters is registering and can be cleared"""
        sr = Common_setup()

        # START TRAFFIC
        ixia_result = Verify.ixia_traffic_rx(stream_list)

        output = sr.r1.execute('show controllers np counters all | i SR')
        mo = re.search(r'SRH_PASS2 +(\d+)', output)

        if int(mo.group(1)) >= 190000:
            print('Pass SRH NP counter found pkts matched {}'.format(mo.group(1)))
        else:
            print('Fail SRH NP counter not found pkts matched {}'.format(mo.group(1)))

        # CLEAR COUNTERS
        Clear.counters(sr.uut_list)


    @aetest.cleanup
    def cleanup(self):
        """Testcase cleanup."""
        # COLLECT DEBUG LOGS

class SrLoopback(aetest.Testcase):
    """Verify SR config with scale loopback configs."""

    debug = 0

    @aetest.setup
    def setup(self):
        """Testcase setup."""
        sr = Common_setup()

        i = 1
        config = '''interface loopback 0
                 '''
        while i <= 10:
            hex_value = dec_to_hex(i)
            slo = ('''ipv6 address 10:10:{}::1/128 segment-routing
                      ipv6-sr prefix-sid
                   ''').format(hex_value)

            config += slo
            i += 1

        log.info(banner('Applying scale loopback config'))
        sr.r1.configure(config)


    @aetest.test
    def scale_loopback_config(self):
        """Testcase execution."""
        sr = Common_setup()
        # SELECT RANDOM VALUE TO VERIFY CEF OF LOOPBACKS
        num = random.sample(range(1, 10), 3)

        for i in num:
            hex_num = dec_to_hex(i)
            pfx = '10:10:{}::1'.format(hex_num)
            log.info('num = {} hex = {} pfx = {}'.format(i, hex_num, pfx))
            result = Verify.srv6_show_cef_pd_check(rtr=sr.r1, lc=uut_lc,
                                                   prefix=pfx)
            if result == 1:
                self.failed('SRv6 PD check failed')

    @aetest.cleanup
    def cleanup(self):
        """Testcase cleanup."""
        sr = Common_setup()

        i = 1
        unconfig = '''interface loopback 0
                   '''
        while i <= 10:
            hex_value = dec_to_hex(i)
            slo = ('''no ipv6 address 10:10:{}::1/128 segment-routing
                   ''').format(hex_value)

            unconfig += slo
            i += 1

        log.info(banner('Removing scale loopback config'))
        sr.r1.configure(unconfig)

        # COLLECT DEBUG LOGS

class SrFeatureInteraction(aetest.Testcase):
    """Verify SR feature interaction."""

    debug = 0

    @aetest.setup
    def setup(self):
        """Testcase setup."""
        sr = Common_setup()

        # 1. CONFIG IPV6 ACL
        sr.r1.configure("""ipv6 access-list srv6_acl1
                        deny ipv6 any host 192:168:1::1
                        permit ipv6 any any""")

        # APPLY ACL TO INTERFACE
        sr.r1.configure("""interface {}
                         ipv6 access-group srv6_acl1 ingress""".format(
                                                     tclstr(sr.r1_tgen_intfs)))

        # 2. CONFIG NETFLOW
        sr.r1.configure('''flow monitor-map fmm
                         record ipv6
                         cache entries 10000
                         cache timeout active 1000
                         cache timeout inactive 1000''')

        sr.r1.configure('''sampler-map fsm1
                        random 1 out-of 1''')

        sr.r1.configure('''interface {}
                        flow ipv6 monitor fmm sampler fsm1 ingress'''.format(
                                                      tclstr(sr.r1_tgen_intfs)))

    @aetest.test
    def SrAcl(self):
        """Testcase execution."""

        sr = Common_setup()
        # SEND TRAFFIC
        sr.ixia.traffic_control(action='run', port_handle=sr.port_handle_list)
        time.sleep(30)

        acl_drop_stream = []
        acl_drop_stream.append(stream_list[0])
        acl_drop_stream.append(stream_list[2])

        # GET PACKET LOSS
        for drop_stream in acl_drop_stream:
            traffic_status = sr.ixia.traffic_stats(mode='stream ',
                                                streams='{} '.format(drop_stream))

            pkt_loss = traffic_status[sr.port_handle_list[2]].stream\
            [drop_stream].rx.loss_percent

            if float(pkt_loss) >= 99:
                log.info('Pass expected ACL traffic to drop and got {} percent traffic '
                       'drop on stream ids {}'.format(pkt_loss,drop_stream))
            else:
                self.failed('Fail ACL traffic did not drop got {} percent traffic '
                       'drop on stream ids {}'.format(pkt_loss,drop_stream))

        # CHECK ACL HW MATCH COUNTERS
        output = sr.r1.execute('show access-lists ipv6 srv6_acl1 hardware ingress '
                                'interface {} location {}'.format(tclstr(sr.r1_tgen_intfs),
                                                                  uut_lc))

        mo = re.search(r'(\d+) hw +matches', output)

        if int(mo.group(1)) >= 395000:
            log.info('Pass ACL HW entreis matched {} expected 400000'.format(mo.group(1)))
        else:
            self.failed('Fail ACL HW entreis matched {} expected 400000'.format(mo.group(1)))

        # UNCONFIG ACL
        sr.r1.configure("""interface {}
                         no ipv6 access-group srv6_acl1 ingress""".format(
                                                     tclstr(sr.r1_tgen_intfs)))
        sr.r1.configure("""no ipv6 access-list srv6_acl1""")

        # CLEAR COUNTERS
        Clear.counters(sr.uut_list)


    @aetest.test
    def SrNetflow(self):
        """Testcase execution."""
        #VERIFY NETFLOW
        sr = Common_setup()

        # SEND TRAFFIC
        ixia_result = Verify.ixia_traffic_rx(stream_list)

        if ixia_result == 1:
            self.failed('traffic failed')

        klist = tcl.q.eval('router_show -device {} '
                           '-cmd show flow monitor fmm cache location {} '
                           '-os_type xr '.format(sr.r1.handle, uut_lc))

        num_flows = klist.cache.flows

        i = 1
        while i <= int(num_flows):
            flow = 'flow{}'.format(i)
            log.info('searching flow {}'.format(flow))
            if (klist[flow].srcadd == '100::1' and klist[flow].dstadd == '192:168:1::1'
                and klist[flow].flow_label == '5000'):
                log.info('Pass found srv6 traffic stream src {} dst {} '
                         'flow label {}'.format(klist[flow].srcadd,
                                                klist[flow].dstadd,
                                                klist[flow].flow_label))
                break
            elif i == int(num_flows):
                self.failed('Fail cound not find srv6 traffic stream src {} '
                            'dst {} flow label {}'.format(klist[flow].srcadd,
                                                          klist[flow].dstadd,
                                                          klist[flow].flow_label))
            else:
                log.info('searching for srv6 traffic stream attempt {}'.format(i))

            i += 1
        # CLEAR COUNTERS
        Clear.counters(sr.uut_list)

    @aetest.test
    def SrSpan(self):
        """Testcase execution."""
        sr = Common_setup()
        sr.r1.configure('''monitor-session srv6_ixia ethernet
                        destination interface {}'''.format(sr.r1_r5_intfs[0]))

        sr.r1.configure('''interface {}
                        monitor-session srv6_ixia ethernet direction rx-only
                        '''.format(tclstr(sr.r1_tgen_intfs)))

        # SEND TRAFFIC
        ixia_result = Verify.ixia_traffic_rx(stream_list)

        if ixia_result == 1:
            self.failed('traffic failed')

        # CHECK NP FOR SPAN COUNTER
        output = sr.r1.execute('show controllers np counters all | i SPAN')
        mo = re.search(r'SPAN_LPBK +(\d+)', output)
        if int(mo.group(1)) >= 290000:
            log.info('Pass SPAN worked for {} packets out of 300000'.format(mo.group(1)))
        else:
            self.failed('Fail SPAN only found {} pkts out of 300000'.format(mo.group(1)))

        # CLEAR COUNTERS
        Clear.counters(sr.uut_list)


    @aetest.cleanup
    def cleanup(self):
        """Testcase cleanup."""
        sr = Common_setup()

        # REMOVE NETFLOW
        sr.r1.configure('''no flow monitor-map fmm
                           no sampler-map fsm1
                           interface {}
                           no flow ipv6 monitor fmm sampler fsm1 ingress
                           '''.format(tclstr(sr.r1_tgen_intfs)))

        # REMOVE SPAN
        sr.r1.configure('''no monitor-session srv6_ixia
                           interface {}
                           no monitor-session srv6_ixia'''.format(
                                                     tclstr(sr.r1_tgen_intfs)))



        # COLLECT DEBUG LOGS

class SrIgp(aetest.Testcase):
    """Verify SR can configure multiple loopbacks."""

    debug = 0

    @aetest.setup
    def setup(self):
        """Testcase setup."""

    @aetest.test
    def test(self):
        """Testcase execution."""



    @aetest.cleanup
    def cleanup(self):
        """Testcase cleanup."""
        print('hi')
        # COLLECT DEBUG LOGS

class Sr_te_path_sr(aetest.Testcase):
    """Verify SR using path option segment routing."""

    debug = 0

    @aetest.setup
    def setup(self):
        """Testcase setup."""
        sr = Common_setup()
        # GET LINECARD LOCATION

        r1_r5_int = [tclstr(sr.rtr1_rtr5_cfg_intf_list), sr.r1_r5_intfs[0]]

        for intf in r1_r5_int:
            sr.r1.configure('interface {} shutdown'.format(intf))

        sr.r1.execute('show mpls forwarding tunnels')

        # REMOVE AUTOROUTE ANNOUNCE FROM ALL TUNNELS
        for r1_r5_tun, r1_r4_tun in itertools.zip_longest(sr.r1_r5_tunnel_list,
                                                          sr.r1_r4_tunnel_list):
            sr.r1.configure('''interface {}
                            no autoroute announce'''.format(r1_r5_tun))

            sr.r1.configure('''interface {}
                            no autoroute announce'''.format(r1_r4_tun))

        # ADDING AUTOROUTE ANNOUNCE BACK TO SINGLE TUNNEL
        sr.r1.configure('''interface {}
                        autoroute announce'''.format(sr.r1_r5_tunnel_list[0]))

        sr.r1.configure('''interface {}
                        autoroute announce'''.format(sr.r1_r4_tunnel_list[0]))
        # ADD AUTOROUTE ANNOUNCE FOR SR TUNNEL

    @aetest.test
    def test(self):
        """Testcase execution."""
        log.info("Testcase sr_te_path_sr")
        sr = Common_setup()
        self.debug = 0
        # 1. CLEAR COUNTERS
        Clear.counters(sr.uut_list)

        # 2. VERIFY FWD OVER TUNNEL
        result = Verify.route(sr.r1, [sr.r4_lo, sr.r5_lo],
                             [sr.r1_r4_tunnel_list[0], sr.r1_r5_tunnel_list[0]])

        if result == 1:
            self.failed('tunnel fwd was not as expected')

        # 3. SEND TRAFFIC

        ixia_result = Verify.ixia_traffic_rx(stream_list)

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
        sr = Common_setup()

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
        sr = Common_setup()

        # 1. CLEAR COUNTERS
        Clear.counters(sr.uut_list)

        # 2. VERIFY FWD OVER TUNNEL
        result = Verify.route(sr.r1, [sr.r4_lo, sr.r5_lo],
                             [sr.r1_r4_tunnel_list[1], sr.r1_r5_tunnel_list[1]])

        if result == 1:
            self.debug = 1
            self.failed('tunnel fwd was not as expected')

        # 3. SEND TRAFFIC
        ixia_result = Verify.ixia_traffic_rx(stream_list)

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
        sr = Common_setup()

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
        sr = Common_setup()

        # 1. CLEAR COUNTERS
        Clear.counters(sr.uut_list)

        # 2. VERIFY FWD OVER TUNNEL
        result = Verify.route(sr.r1, [sr.r4_lo, sr.r5_lo],
                             [sr.r1_r4_tunnel_list[2], sr.r1_r5_tunnel_list[2]])

        if result == 1:
            self.debug = 1
            self.failed('tunnel fwd was not as expected')

        # 3. SEND TRAFFIC
        ixia_result = Verify.ixia_traffic_rx(stream_list)

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
        sr = Common_setup()

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
        sr = Common_setup()
        # 1. CLEAR COUNTERS
        Clear.counters(sr.uut_list)

        # 2. VERIFY FWD OVER TUNNEL
        result = Verify.route(sr.r1, [sr.r4_lo, sr.r5_lo],
                             [sr.r1_r4_tunnel_list[3], sr.r1_r5_tunnel_list[3]])

        if result == 1:
            self.debug = 1
            self.failed('tunnel fwd was not as expected')

        # 3. SEND TRAFFIC
        ixia_result = Verify.ixia_traffic_rx(stream_list)

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
        sr = Common_setup()

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
        sr = Common_setup()

        # 1. CLEAR COUNTERS
        Clear.counters(sr.uut_list)

        # 2. VERIFY FWD OVER TUNNEL
        result = Verify.route(sr.r1, [sr.r4_lo, sr.r5_lo],
                             [sr.r1_r4_tunnel_list[4], sr.r1_r5_tunnel_list[4]])

        if result == 1:
            self.debug = 1
            self.failed('tunnel fwd was not as expected')

        # 3. SEND TRAFFIC
        ixia_result = Verify.ixia_traffic_rx(stream_list)

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
        sr = Common_setup()

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
        sr = Common_setup()

        # 1. CLEAR COUNTERS
        Clear.counters(sr.uut_list)

        # 2. VERIFY FWD OVER TUNNEL
        result = Verify.route(sr.r1, [sr.r4_lo, sr.r5_lo],
                             [sr.r1_r4_tunnel_list[5], sr.r1_r5_tunnel_list[5]])

        if result == 1:
            self.debug = 1
            self.failed('tunnel fwd was not as expected')

        # 3. SEND TRAFFIC
        ixia_result = Verify.ixia_traffic_rx(stream_list)

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
        sr = Common_setup()

        # COLLECT DEBUG LOGS
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])


class Rsp_failover_fail_back(aetest.Testcase):
    """Verify SR after RSP failover then failback."""

    debug = 0

    @aetest.setup
    def setup(self):
        """Testcase setup."""
        sr = Common_setup()

        if sr.te_flag == True:
            # SELECTING RANDOM NUMBER FOR TUNNEL
            # REMOVING AA FROM TUN 146 AND 156. ADDING AA TO RANDOM SELECTED TUNNEL
            autoroute_announce(sr.r1,
                               [sr.r1_r4_tunnel_list[5], sr.r1_r5_tunnel_list[5]],
                               [sr.r1_r4_tunnel_list[random_tun_num],
                               sr.r1_r5_tunnel_list[random_tun_num]])

    @aetest.test
    def test(self):
        """Testcase execution."""
        sr = Common_setup()
        attempts = 2
        i = 1
        while i <= attempts:

            log.info(banner('RSP SWITCHOVER ATTEMPT {}'.format(i)))

            # 1. CLEAR COUNTERS
            Clear.counters(sr.uut_list)

            if sr.te_flag == True:
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
            ixia_result = Verify.ixia_traffic_rx(stream_list)

            if ixia_result == 1:
                self.debug = 1
                self.failed('traffic failed')

            if fo_status == 0:
                self.debug = 1
                self.failed('switchover failed')

            if sr.te_flag == True:
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
        sr = Common_setup()

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
        sr = Common_setup()
        process = SrScriptArgs.rsp_process_list
        log.info(banner('RSP RESTART PROCESS {}'.format(process[self.p_index])))

        # 1. CLEAR COUNTERS
        Clear.counters(sr.uut_list)

        if sr.te_flag == True:
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
        ixia_result = Verify.ixia_traffic_rx(stream_list)

        if ixia_result == 1:
            self.debug = 1
            self.failed('traffic failed')

        if sr.te_flag == True:
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
        sr = Common_setup()
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
        sr = Common_setup()
        process = SrScriptArgs.lc_process_list

        log.info(banner('LC RESTART PROCESS {}'.format(process[self.p_index])))

        # 1. CLEAR COUNTERS
        Clear.counters(sr.uut_list)

        if sr.te_flag == True:
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
        ixia_result = Verify.ixia_traffic_rx(stream_list)

        if ixia_result == 1:
            self.debug = 1
            self.failed('traffic failed')

        if sr.te_flag == True:
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
        sr = Common_setup()

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
        sr = Common_setup()

        # RELOADING LC
        lc_result = tcl.q.eval('::xr::utils::switchover_time '
                               '-device {} '
                               '-data_check 0 '
                               '-switchover_type hw_module '
                               '-return_state_timeout 300 '
                               '-hw_module_location {} '
                               .format(sr.r1.handle, uut_lc))
        time.sleep(30)
        # VERIFY IF LC RELOAD WAS SUCCESSFUL
        if lc_result == 0:
            self.debug = 1
            self.failed('lc reload failed')

        if sr.vpls_flag == True:
            # VERIFY L2VPN IS UP
            l2vpn_result = Verify.l2vpn(sr.r1, [sr.r4_lo, sr.r5_lo])
            if l2vpn_result != 0:
                self.debug = 1
                self.failed('l2vpn verify failed on {}'.format(sr.r1))

        # VERIFY IGP IS UP
        isis_result = Verify.routing_protocol(sr.r1, sr.exp_isis_prx,
                                              protocol=proto)
        if isis_result != 0:
            self.debug = 1
            self.failed('isis verify failed on {}'.format(sr.r1))

        if sr.te_flag == True:
            # VERIFY TUNNEL IS UP
            tun_result = Verify.te_tunnels(sr.r1, 0,
                                           [sr.r1_r4_tunnel_list[random_tun_num],
                                            sr.r1_r5_tunnel_list[random_tun_num]])
            if tun_result == 1:
                self.debug = 1
                self.failed('tunnels did not come up')

        # 1. CLEAR COUNTERS
        Clear.counters(sr.uut_list)

        if sr.te_flag == True:
            # 2. VERIFY FWD OVER TUNNEL
            result = Verify.route(sr.r1, [sr.r4_lo, sr.r5_lo],
                                  [sr.r1_r4_tunnel_list[random_tun_num],
                                  sr.r1_r5_tunnel_list[random_tun_num]])

            if result == 1:
                self.debug = 1
                self.failed('tunnel fwd was not as expected')

        # 3. SEND TRAFFIC
        ixia_result = Verify.ixia_traffic_rx(stream_list)

        if ixia_result == 1:
            self.debug = 1
            self.failed('traffic failed')

        if sr.te_flag == True:
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
        sr = Common_setup()

        # COLLECT DEBUG LOGS
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])


class Interface_flap_tunnel(aetest.Testcase):
    """Verify SR while flapping the SR tuneles."""

    debug = 0

    @aetest.setup
    def setup(self):
        """Testcase setup."""

    @aetest.test
    def test(self):
        """Testcase execution."""
        sr = Common_setup()
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
        ixia_result = Verify.ixia_traffic_rx(stream_list)

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
        sr = Common_setup()

        # COLLECT DEBUG LOGS
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])


class Remove_add_config_loopback(aetest.Testcase):
    """Verify SR while removing R4 and R5 loopback configs."""

    debug = 0

    @aetest.setup
    def setup(self):
        """Testcase setup."""

    @aetest.test
    def test(self):
        """Testcase execution."""
        sr = Common_setup()
        attempts = 3
        i = 1
        while i <= attempts:
            log.info(banner('removing loopback config attempt {}'.format(i)))

            # REMOVE LOOPBACK
            if sr.srv6_flag == True:
                log.info(sr.r1.configure('no interface loopback0'))

                # ENSURE SRV6 PD FLAG IS NO LONGER ENABLED
                result = Verify.srv6_show_cef_pd_check(rtr=sr.r1, lc=uut_lc,
                                                       pd_flag='off')
                if result == 1:
                    self.failed('SRv6 PD check failed')
            else:
                log.info(sr.r4.configure('no interface loopback0'))
                log.info(sr.r5.configure('no interface loopback0'))

            time.sleep(60)

            # ROLLING BACK LOOBACK CONFIG
            if sr.srv6_flag == True:
                sr.r1.execute('rollback config last 1')
            else:
                sr.r4.execute('rollback config last 1')
                sr.r5.execute('rollback config last 1')

            time.sleep(60)

            if sr.te_flag == True:
                # VERIFY ROUTE IS OVER TUNNEL
                result = Verify.route(sr.r1, [sr.r4_lo, sr.r5_lo],
                                      [sr.r1_r4_tunnel_list[random_tun_num],
                                       sr.r1_r5_tunnel_list[random_tun_num]])
                if result == 1:
                    self.debug = 1
                    self.failed('tunnel fwd was not as expected')

            if sr.vpls_flag == True:
                # VERIFY L2VPN IS UP
                l2vpn_result = Verify.l2vpn(sr.r1, [sr.r4_lo, sr.r5_lo])
                if l2vpn_result != 0:
                    self.debug = 1
                    self.failed('l2vpn verify failed on {}'.format(sr.r1))

            if sr.srv6_flag == True:
                # ENSURE PD FLAG IS ENABLED
                result = Verify.srv6_show_cef_pd_check(rtr=sr.r1, lc=uut_lc)
                if result == 1:
                    self.failed('SRv6 PD check failed')

            i += 1

            # 1. CLEAR COUNTERS
            Clear.counters(sr.uut_list)

            # 2. SEND TRAFFIC
            ixia_result = Verify.ixia_traffic_rx(stream_list)

            if ixia_result == 1:
                self.debug = 1
                self.failed('traffic failed')

            if sr.te_flag == True:
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
        sr = Common_setup()

        # COLLECT DEBUG LOGS
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])


class Remove_add_config_l2vpn(aetest.Testcase):
    """Verify SR while adding and remving L2VPN config."""

    debug = 0

    @aetest.setup
    def setup(self):
        """Testcase setup."""

    @aetest.test
    def test(self):
        """Testcase execution."""
        sr = Common_setup()
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
        ixia_result = Verify.ixia_traffic_rx(stream_list)

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
        sr = Common_setup()

        # COLLECT DEBUG LOGS
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])


class Remove_add_config_igp(aetest.Testcase):
    """Verify SR while adding and removing the IGP config."""

    debug = 0

    @aetest.setup
    def setup(self):
        """Testcase setup."""

    @aetest.test
    def test(self):
        """Testcase execution."""
        sr = Common_setup()
        attempts = 2
        i = 1
        while i <= attempts:

            log.info(banner('removing igp config attempt {}'.format(i)))

            sr.r1.configure('no router {} 1'.format(proto))
            sr.r1.execute('''rollback config last 1''')

            i += 1

        time.sleep(30)
        # VERIFY L2VPN IS UP
        if sr.vpls_flag == True:
            l2vpn_result = Verify.l2vpn(sr.r1, [sr.r4_lo, sr.r5_lo])
            if l2vpn_result != 0:
                self.debug = 1
                self.failed('l2vpn verify failed on {}'.format(sr.r1))

        # VERIFY IGP IS UP
        isis_result = Verify.routing_protocol(sr.r1, sr.exp_isis_prx,
                                              protocol=proto)
        if isis_result != 0:
            self.debug = 1
            self.failed('isis verify failed on {}'.format(sr.r1))

        # VERIFY TUNNEL IS UP
        if sr.te_flag == True:
            tun_result = Verify.te_tunnels(sr.r1, 0,
                                           [sr.r1_r4_tunnel_list[random_tun_num],
                                            sr.r1_r5_tunnel_list[random_tun_num]])
            if tun_result == 1:
                self.debug = 1
                self.failed('tunnels did not come up')

        # 1. CLEAR COUNTERS
        Clear.counters(sr.uut_list)

        # 2. SEND TRAFFIC
        ixia_result = Verify.ixia_traffic_rx(stream_list)

        if ixia_result == 1:
            self.debug = 1
            self.failed('traffic failed')

        # 3. VERIFY TRAFFIC STATS
        if sr.te_flag == True:
            result = Verify.interface_counters(sr.r1.handle,
                                               [sr.r1_r4_tunnel_list[random_tun_num],
                                               sr.r1_r5_tunnel_list[random_tun_num]])
            if result == 1:
                self.debug = 1
                self.failed('interface traffic accounting failed')

    @aetest.cleanup
    def cleanup(self):
        """Testcase cleanup."""
        sr = Common_setup()

        # COLLECT DEBUG LOGS
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])


class Interface_flap_main_interface(aetest.Testcase):
    """Verify SR and flap the main interface."""

    debug = 0

    @aetest.setup
    def setup(self):
        """Testcase setup."""
        # REMOVE RANDOM TUNNEL NUMBERING AS IT COULD SELECT A TUNNEL THAT
        # IS CONFIGURED FOR EXPLICIT PATH. FOR THE FOLLOWING TEST CASES YOU
        # WILL NEED TO USE DYNAMIC TUNNELS
        sr = Common_setup()
        # REMOVING AA FROM TUN 146 AND 156. ADDING AA TO RANDOM SELECTED TUNNEL
        if sr.te_flag == True:
            autoroute_announce(sr.r1,
                               [sr.r1_r4_tunnel_list[random_tun_num],
                                sr.r1_r5_tunnel_list[random_tun_num]],
                               [sr.r1_r4_tunnel_list[dynamic_tun_num],
                                sr.r1_r5_tunnel_list[dynamic_tun_num]])

            # GETTING TUNNEL ID
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
            # SHUT DOWN ALL INTERFACES EXCEPT LOOPBACK AND MAIN INTF
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
        sr = Common_setup()
        # VERIFY IGP HAS 1 ADJ / NEIGHBOR
        isis_result = Verify.routing_protocol(sr.r1, sr.pfx,
                                              protocol=proto)

        if isis_result != 0:
            self.debug = 1
            self.failed('isis verify failed on {}'.format(sr.r1))

        # GET IGP INTERFACE
        klist = tcl.q.eval('router_show -device {} '
                           '-cmd show isis adjacency '
                           '-os_type xr '.format(sr.r1.handle))

        igp_intf = klist.adjacencies[sr.adj].intf

        if sr.te_flag == True:
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

        # FLAPPING MAIN INTERFACE
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

            # VERIFY IGP IS UP AFTER INTERFACE FLAP
            isis_result = Verify.routing_protocol(sr.r1, sr.pfx,
                                                  protocol=proto)
            if isis_result != 0:
                self.debug = 1
                self.failed('isis verify failed on {}'.format(sr.r1))

            if sr.te_flag == True:
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
            ixia_result = Verify.ixia_traffic_rx(stream_list)

            if ixia_result == 1:
                self.debug = 1
                self.failed('traffic failed')

            # 3. VERIFY TRAFFIC STATS
            if sr.te_flag == True:
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
        sr = Common_setup()

        # COLLECT DEBUG LOGS
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])


class Interface_flap_bundle(aetest.Testcase):
    """Verify SR and flap the logical bundle interface."""

    debug = 0

    @aetest.setup
    def setup(self):
        """Testcase setup."""

    @aetest.test
    def test(self):
        """Testcase execution."""
        sr = Common_setup()

        # UNSHUT BUNDLE
        sr.r1.configure('''interface {}
                        no shutdown'''.format(sr.r1_all_intfs[3]))
        time.sleep(10)
        # SHUT MAIN INTERFACE
        sr.r1.configure('''interface {} shutdown'''.format(sr.r1_all_intfs[0]))

        # VERIFY IGP HAS 1 ADJ / NEIGHBOR
        igp_result = Verify.routing_protocol(sr.r1, sr.pfx,
                                             protocol=proto)
        if igp_result != 0:
            self.debug = 1
            self.failed('igp verify failed on {}'.format(sr.r1))

        # GET IGP INTERFACE
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

            igp_intf = klist.adjacencies[sr.adj].intf

        if sr.te_flag == True:
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

        # FLAPPING BUNDLE INTERFACE
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
            isis_result = Verify.routing_protocol(sr.r1, sr.pfx,
                                                  protocol=proto)
            if isis_result != 0:
                self.debug = 1
                self.failed('isis verify failed on {}'.format(sr.uut_list[3]))

            # VERIFY TUNNEL IS UP
            if sr.te_flag == True:
                tun_result = Verify.te_tunnels(sr.r1, 0,
                                               [sr.r1_r4_tunnel_list[dynamic_tun_num],
                                                sr.r1_r5_tunnel_list[dynamic_tun_num]])
                if tun_result == 1:
                    self.debug = 1
                    self.failed('tunnels did not come up')

            # 1. CLEAR COUNTERS
            Clear.counters(sr.uut_list)

            # 2. SEND TRAFFIC
            ixia_result = Verify.ixia_traffic_rx(stream_list)

            if ixia_result == 1:
                self.debug = 1
                self.failed('traffic failed')

            # 3. VERIFY TRAFFIC STATS
            if sr.te_flag == True:
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
        sr = Common_setup()

        # COLLECT DEBUG LOGS
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])


class Interface_flap_bundle_members(aetest.Testcase):
    """Verify SR over bundle, and flap bundle interface members."""

    debug = 0

    @aetest.setup
    def setup(self):
        """Testcase setup."""

    @aetest.test
    def test(self):
        """Testcase execution."""
        sr = Common_setup()
        # SHUTING DOWN BUNDLE MEMBERS
        i = 1
        for intfs in sr.r1_r2_intfs[1:3]:
            print('i = {}'.format(i))
            log.info(banner('''for BE12 shutting down intf {}
                            '''.format(intfs)))
            sr.r1.configure('interface {} shutdown'.format(intfs))
            print(sr.r1.execute('show interface bundle-ether12'.format(intfs)))
            time.sleep(5)
            if i == 2:
                # NO NEED TO CHECK TRAFFIC STATS ONCE ALL BUNDLE MEMBERS ARE
                # SHUTDOWN AS IGP WILL GO DOWN AS WELL.
                continue
            else:
                # 1. CLEAR COUNTERS
                Clear.counters(sr.uut_list)

                # 2. SEND TRAFFIC
                ixia_result = Verify.ixia_traffic_rx(stream_list)

                if ixia_result == 1:
                    self.debug = 1
                    self.failed('traffic failed')

                # 3. VERIFY TRAFFIC STATS
                if sr.te_flag == True:
                    result = Verify.interface_counters(sr.r1.handle,
                                                       [sr.r1_r4_tunnel_list[dynamic_tun_num],
                                                       sr.r1_r5_tunnel_list[dynamic_tun_num]])
                    if result == 1:
                        self.debug = 1
                        self.failed('interface traffic accounting failed')

            i += 1

        i = 1
        # BRINING BUNDLE MEMBERS BACK UP WITH NO SHUT
        for intfs in reversed(sr.r1_r2_intfs[1:3]):
            log.info(banner('''for BE12 brining intf {} back up with no shut
                            '''.format(intfs)))
            sr.r1.configure('''interface {}
                          no shutdown'''.format(intfs))

            # VERIFY CONTROL PLANE IS UP
            if i == 1:

                # CHECK IF IGP IS UP
                isis_result = Verify.routing_protocol(sr.r1, sr.pfx,
                                                      protocol=proto)
                if isis_result != 0:
                    self.debug = 1
                    self.failed('isis verify failed on {}'.format(sr.r1))

                # CHECK IF L2VPN IS UP
                if sr.vpls_flag == True:
                    l2vpn_result = Verify.l2vpn(sr.r1, [sr.r4_lo, sr.r5_lo])
                    if l2vpn_result != 0:
                        self.debug = 1
                        self.failed('l2vpn verify failed on {}'.format(sr.r1))

                # CHECK IF TUNNELS ARE UP
                if sr.te_flag == True:
                    tun_result = Verify.te_tunnels(sr.r1, 0,
                                                   [sr.r1_r4_tunnel_list[dynamic_tun_num],
                                                    sr.r1_r5_tunnel_list[dynamic_tun_num]])
                    if tun_result == 1:
                        self.fdebug = 1
                        self.failed('tunnels did not come up')

            # 1. CLEAR COUNTERS
            Clear.counters(sr.uut_list)

            # 2. SEND TRAFFIC
            ixia_result = Verify.ixia_traffic_rx(stream_list)

            if ixia_result == 1:
                self.debug = 1
                self.failed('traffic failed')

            # 3. VERIFY TRAFFIC STATS
            if sr.te_flag == True:
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
        sr = Common_setup()

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
        sr = Common_setup()
        # REMOVING BUNDLE MEMBERS
        i = 1
        for intfs in sr.r1_r2_intfs[1:3]:

            log.info(banner('''for BE12 removing intf {} '''.format(intfs)))
            sr.r1.configure('''interface {}
                            no bundle id'''.format(intfs))
            print(sr.r1.execute('show interface bundle-ether12'.format(intfs)))
            time.sleep(5)
            if i == 2:
                # NO NEED TO CHECK TRAFFIC STATS ONCE ALL BUNDLE MEMBERS ARE
                # REMOVED AS IGP WILL GO DOWN AS WELL.
                time.sleep(30)
                continue
            else:
                # 1. CLEAR COUNTERS
                Clear.counters(sr.uut_list)

                # 2. SEND TRAFFIC
                ixia_result = Verify.ixia_traffic_rx(stream_list)

                if ixia_result == 1:
                    self.debug = 1
                    self.failed('traffic failed')

                # 3. VERIFY TRAFFIC STATS
                if sr.te_flag == True:
                    result = Verify.interface_counters(sr.r1.handle,
                                                       [sr.r1_r4_tunnel_list[dynamic_tun_num],
                                                       sr.r1_r5_tunnel_list[dynamic_tun_num]])
                    if result == 1:
                        self.debug = 1
                        self.failed('interface traffic accounting failed')

            i += 1

        i = 1
        # BRINING BUNDLE MEMBERS BACK UP WITH NO SHUT
        for intfs in reversed(sr.r1_r2_intfs[1:3]):
            log.info(banner('''for BE12 adding interface {} back to bundle
                            '''.format(intfs)))
            sr.r1.configure('''interface {}
                            bundle id 12 mode active'''.format(intfs))
            time.sleep(5)
            print(sr.r1.execute('show interface bundle-ether12'.format(intfs)))

            # VERIFY CONTROL PLANE IS UP
            if i == 1:

                # CHECK IF IGP IS UP
                isis_result = Verify.routing_protocol(sr.r1, sr.pfx,
                                                      protocol=proto)
                if isis_result != 0:
                    self.debug = 1
                    self.failed('isis verify failed on {}'.format(sr.r1))

                # CHECK IF L2VPN IS UP
                if sr.vpls_flag == True:
                    l2vpn_result = Verify.l2vpn(sr.r1, [sr.r4_lo, sr.r5_lo])
                    if l2vpn_result != 0:
                        self.debug = 1
                        self.failed('l2vpn verify failed on {}'.format(sr.r1))

                # CHECK IF TUNNELS ARE UP
                if sr.te_flag == True:
                    tun_result = Verify.te_tunnels(sr.r1, 0,
                                                   [sr.r1_r4_tunnel_list[dynamic_tun_num],
                                                    sr.r1_r5_tunnel_list[dynamic_tun_num]])
                    if tun_result == 1:
                        self.debug = 1
                        self.failed('tunnels did not come up')

            # 1. CLEAR COUNTERS
            Clear.counters(sr.uut_list)

            # 2. SEND TRAFFIC
            ixia_result = Verify.ixia_traffic_rx(stream_list)

            if ixia_result == 1:
                self.debug = 1
                self.failed('traffic failed')

            # 3. VERIFY TRAFFIC STATS
            if sr.te_flag == True:
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
        sr = Common_setup()

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
        sr = Common_setup()

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
            ixia_result = Verify.ixia_traffic_rx(stream_list)

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
            ixia_result = Verify.ixia_traffic_rx(stream_list)

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
        sr = Common_setup()

        # COLLECT DEBUG LOGS
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])

class Sr_Ecmp(aetest.Testcase):
    """Verify SR ECMP."""

    debug = 0

    @aetest.setup
    def setup(self):
        """Testcase setup."""
        sr = Common_setup()

        # ENABLE FLOW LABEL CONFIG
        if sr.srv6_flag == True:
            isis_expected_adj = 4
            sr.r1.configure('cef load-balancing fields ipv6 flow-label')

            # BRING UP ALL THE PHYSICAL PATHS
            for intfs in sr.rtr1_rtr2_cfg_intf_list:

                print(sr.r1.configure('''interface {}
                                         no shutdown'''.format(intfs)))

            for intfs in sr.r1_r2_intfs:

                print(sr.r1.configure('''interface {}
                                         no shutdown'''.format(intfs)))

        # VERIFY ALL IGP PATHS ARE UP
        igp_result = Verify.routing_protocol(sr.r1, isis_expected_adj,
                                              protocol=proto)

        if igp_result == 1:
            self.failed('did not find expected isis adj')

    @aetest.test
    def test(self):
        """Testcase execution."""
        sr = Common_setup()

        if sr.srv6_flag == True:
            # CREATE LIST OF ECMP IGP INTERFACES
            ecmp_intf = []
            for i in range(len(sr.rtr1_rtr2_cfg_intf_list)):
                ecmp_intf.append(sr.rtr1_rtr2_cfg_intf_list[i])

            ecmp_intf.append(sr.r1_r2_intfs[0])

        # CREATE LIST OF ECMP TRAFFIC STREAMS
        ecmp_traffic_stream = []
        ecmp_traffic_stream.append(stream_list[0])

        # 1. CLEAR COUNTERS
        Clear.counters(sr.uut_list)

        #2. SEND TRAFFIC
        ixia_result = Verify.ixia_traffic_rx(ixia_result=0,
                                             packet_tolerance=5.000,
                                             wait_time=60,
                                             stream_hld=ecmp_traffic_stream)

        if ixia_result == 1:
            self.debug = 1
            self.failed('traffic failed')

        #3. STOP TRAFFIC STREAM
        sr.ixia.traffic_control(action='stop', handle=ecmp_traffic_stream)


        # VERIFY ECMP TRAFFIC ON LINK
        pkt_count_list = []
        for intfs in ecmp_intf:
            klist = tcl.q.eval('router_show -device {} '
                               '-cmd show interface {} accounting '
                               '-os_type xr '.format(sr.r1.handle, intfs))

            pkts_out_intf = klist.totals.pkts_out

            # ENSURE NOT TO MUCH TRAFFIC WHEN OVER SINGLE LINK
            log.info('interface {} pkts out = {}'.format(intfs,pkts_out_intf))
            if int(pkts_out_intf) >= 40000:
                self.failed('Fail, To much traffic on single link {}'.format(intfs))

            # ADD PKTS TO LIST
            pkt_count_list.append(int(pkts_out_intf))

        # GET TOTAL OF PKT COUNT
        total_pkts = sum(pkt_count_list)

        if total_pkts < 95000:
            self.failed('Fail, Not all ECMP traffic was accounted. '
                   'Expected 100000 got {}'.format(total_pkts))


    @aetest.cleanup
    def cleanup(self):
        """Testcase cleanup."""
        sr = Common_setup()


class Prefered_path(aetest.Testcase):
    """Verify SR with prefered path config."""


    debug = 0

    @aetest.setup
    def setup(self):
        """Testcase setup."""
        sr = Common_setup()
        # BRING UP ALL THE PHYSICAL PATHS
        for intfs in sr.rtr1_rtr2_cfg_intf_list:

            print(sr.r1.configure('''interface {}
                                     no shutdown'''.format(intfs)))

        for intfs in sr.r1_r2_intfs:

            print(sr.r1.configure('''interface {}
                                     no shutdown'''.format(intfs)))

        # ADD AUTOROUTE ANNOUNCE TO ALL TUNNELS
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
        sr = Common_setup()

        # 1. CLEAR COUNTERS
        Clear.counters(sr.uut_list)

        # 2. SEND TRAFFIC
        ixia_result = Verify.ixia_traffic_rx(stream_list)

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
        sr = Common_setup()

        # COLLECT DEBUG LOGS
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])


class Prefered_path_change_tunnel_config(aetest.Testcase):
    """Verify an place modification of the prefered path tunnel config."""

    debug = 0

    @aetest.setup
    def setup(self):
        """Testcase setup."""
        sr = Common_setup()

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
        sr = Common_setup()

        # 1. CLEAR COUNTERS
        Clear.counters(sr.uut_list)

        # 2. SEND TRAFFIC
        ixia_result = Verify.ixia_traffic_rx(stream_list)

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
        sr = Common_setup()

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
        sr = Common_setup()

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
        sr = Common_setup()

        # 1. CLEAR COUNTERS
        Clear.counters(sr.uut_list)

        # 2. SEND TRAFFIC
        ixia_result = Verify.ixia_traffic_rx(stream_list)


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
        sr = Common_setup()

        # COLLECT DEBUG LOGS
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])


class Sr_flow_label_64_Ecmp(aetest.Testcase):
    """Verify SR traffic using flow label.
    Test that MCAST VPLS traffic is going over 64 ECMP tunnels.
    """

    debug = 0

    @aetest.setup
    def setup(self):
        """Testcase setup."""
        sr = Common_setup()

        # REMOVE PREFERED PATH
        for i in range(1,3):
            sr.r1.configure('''l2vpn
                                pw-class my_pref_path_{}
                                encapsulation mpls
                                no preferred-path
                                '''.format(str(i)))

        # BRING UP 64 TE TUNNELS
        if sr.vpls_flag == True:
            isis_expected_adj = 3
            # REMOVE AUTOROUTE ANNOUNCE FOR NON ECMP TUNNELS
            for i in range(2):
                if i == 0:
                    tun_range = '141-146'
                    tun_range64 = '1-64'
                    tun_dst = sr.r4_lo

                    # ENABLE ISIS FOR 64 ECMP PATHS
                    sr.r1.configure('''router isis 1
                                       address-family ipv4 unicast
                                       maximum-paths 64''')

                else:
                    tun_range = '151-156'
                    tun_range64 = '65-128'
                    tun_dst = sr.r5_lo

                # REMOVE AA FROM TUNNELS TO ENDPOINT R5 AND R4
                sr.r1.configure('''interface tunnel-te {}
                                   no autoroute announce'''.format(tun_range))

                # CONFIG 64 ECMP TUNNELS TO R5 AND R4 ENDPOINTS
                sr.r1.configure('''interface tunnel-te {}
                                   ipv4 unnumbered Loopback0
                                   autoroute announce
                                   destination {}
                                   path-option 1 dynamic segment-routing
                                   '''.format(tun_range64, tun_dst))


            for endpoints in [sr.r5_lo, sr.r4_lo]:
                log.info(banner('Checking CEF has 64 entries to '
                                'tunnel dst endpoint {}'.format(endpoints)))

                for i in range(5):
                    # CHECK CEF HAS 64 ENTRIES TO DESTINATION
                    klist = tcl.q.eval('router_show -device {} '
                                       '-cmd show cef {} '
                                       '-os_type xr '.format(sr.r1.handle,
                                                             endpoints))

                    num_of_next_hops = klist.next_hop_count

                    if int(num_of_next_hops) == 64:
                        log.info('Pass found 64 tunnel ECMP '
                                 'entries in cef to endpoint {}'.format(endpoints))
                        break
                    elif i == 4:
                        self.failed('Fail found 64 tunnel ECMP '
                                 'entries in cef to endpoint {}'.format(endpoints))
                    else:
                        log.info('polling for 64 tunnel entries in cef.')
                        time.sleep(10)


    @aetest.test
    def test(self):
        """Testcase execution."""
        sr = Common_setup()

        # 1. CLEAR COUNTERS
        Clear.counters(sr.uut_list)

        # 2. SEND TRAFFIC MCAST TRAFFIC (ECMP ONLY ON TUNNELS
        # NOT SUPPORTED ON IGP LINK FOR MCAST)
        ixia_result = Verify.ixia_traffic_rx(stream_list[2])

        #2A. STOP TRAFFIC STREAM
        sr.ixia.traffic_control(action='stop', handle=stream_list[2])

        if ixia_result == 1:
            self.debug = 1
            self.failed('traffic failed')

        #3. VERIFY ECMP TRAFFIC ON LINK
        for attempts in range(1,3):
            if attempts == 1:
                start_num = 1
                end_num = 65
                endpoint = sr.r5_lo
            if attempts == 2:
                start_num = 65
                end_num = 129
                endpoint = sr.r4_lo
            pkt_count_list = []
            log.info(banner('Checking 64 ecmp to '
                            'tunnel endpoint {}'.format(endpoint)))
            for intfs in range(start_num,end_num):
                klist = tcl.q.eval('router_show -device {} '
                                   '-cmd show interface tunnel-te{} accounting '
                                   '-os_type xr '.format(sr.r1.handle, intfs))

                pkts_out_intf = klist.totals.pkts_out

                # ENSURE NOT TO MUCH TRAFFIC WHEN OVER SINGLE LINK
                log.info('interface tunnel-te{} '
                         'pkts out = {}'.format(intfs, pkts_out_intf))
                if int(pkts_out_intf) >= 3000:
                    self.failed('Fail, To much traffic on '
                                'single link {}'.format(intfs))

                # ADD PKTS TO LIST
                pkt_count_list.append(int(pkts_out_intf))

            # GET TOTAL OF PKT COUNT
            total_pkts = sum(pkt_count_list)

            if total_pkts >= 95000:
                log.info('Pass for 64 ecmp tunnels to end point {} '
                      'pkts sent is {}'.format(endpoint, total_pkts))
            else:
                self.failed('Fail for 64 ecmp tunnels to end point {} '
                      'pkts sent is {}'.format(endpoint, total_pkts))

        # REMOVE TUNNELS FOR 64 ECMP
        sr.r1.configure('''no interface tunnel-te 1-128''')

        # VERIFY TUNNELS ARE REMOVED
        klist = tcl.q.eval('router_show -device {} '
                           '-cmd show mpls traffic-eng tunnels brief '
                           '-os_type xr '.format(sr.r1.handle, intfs))

        output = klist.total_heads_count

        if int(output) >= 13:
            self.failed('Fail 64 ecmp tunnels were not successfully removed')
        else:
            log.info('Pass successfully removed 64 ecmp tunnels')


    @aetest.cleanup
    def cleanup(self):
        """Testcase cleanup."""
        sr = Common_setup()

        # COLLECT DEBUG LOGS
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])


class L2vpn_control_word(aetest.Testcase):
    """Verify SR using control word."""

    debug = 0

    @aetest.setup
    def setup(self):
        """Testcase setup."""
        sr = Common_setup()
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
        sr = Common_setup()

        # 1. CLEAR COUNTERS
        Clear.counters(sr.uut_list)

        # 2. SEND TRAFFIC
        ixia_result = Verify.ixia_traffic_rx(stream_list)

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
        sr = Common_setup()

        # COLLECT DEBUG LOGS
        if self.debug == 1:
            Debug.router(sr.r1, uut_lc, [sr.r4_lo, sr.r5_lo])


class Common_cleanup(aetest.CommonCleanup):
    """Common Cleanup for Sample Test."""

    sr = Common_setup()

    @aetest.subsection
    def post_router_check(self, uut_list=sr.uut_list):
        pass
        #tcl.q.eval('post_router_check {} '.format(uut_list[0].handle))

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
