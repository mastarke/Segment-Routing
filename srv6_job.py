from ats.easypy import run
from ats.datastructures.logic import And, Or, Not
import os


class SrScriptArgs(object):
    """ Segment routing script aruguments."""

    testbed_file = '/ws/mastarke-sjc/my_local_git/segment_routing/sr-vpls.yaml'
    uut_list = ['R6', 'R4', 'R7', 'R2', 'R3']

    # INTERFACE ARGUMENTS TO SELECT LINKS IN COMMON SETUP
    # R1 TO R2 INTERFACES
    r1_r2_num_intfs = 3
    r1_r2_intfs_alias = 'rtr6_rtr4_intf.1'

    # R2 TO R1 INTERFACES
    r2_r1_num_intfs = 3
    r2_r1_intfs_alias = 'rtr4_rtr6_intf.1'

    # R2 TO R3 INTERFACES
    r2_r3_num_intfs = 1
    r2_r3_intfs_alias = 'rtr4_rtr7_intf.1'

    # R3 TO R2 INTERFACES
    r3_r2_num_intfs = 1
    r3_r2_intfs_alias = 'rtr7_rtr4_intf.1'

    # R3 TO R4 INTERFACES
    r3_r4_num_intfs = 1
    r3_r4_intfs_alias = 'rtr7_rtr2_intf.1'

    # R4 TO R3 INTERFACES
    r4_r3_num_intfs = 1
    r4_r3_intfs_alias = 'rtr2_rtr7_intf.1'

    # R4 TO R5 INTERFACES
    r4_r5_num_intfs = 1
    r4_r5_intfs_alias = 'rtr2_rtr3_intf.1'

    # R5 TO R4 INTERFACES
    r5_r4_num_intfs = 1
    r5_r4_intfs_alias = 'rtr3_rtr2_intf.1'

    # FRR LINKS R1 TO R5
    r1_r5_num_intfs = 3
    r1_r5_intfs_alias = 'rtr6_rtr3_intf.1'

    # FRR LINKS R5 TO R1
    r5_r1_num_intfs = 3
    r5_r1_intfs_alias = 'rtr3_rtr6_intf.1'
    #r5_r1_intfs_alias = 'rtr6_rtr3_intf.1'

    # RTR TO TGEN (IXIA) LINKS
    # TGEN1 TO R1 INTERFACES
    r1_tgen1_num_intfs = 1
    r1_tgen1_intfs_alias = 'rtr6_tgen1_intf.1'
    #r1_tgen1_intfs_alias = 'rtr3_tgen1_intf.1'
    r1_tgen1_speed = 'ether10000lan'

    # TGEN1 TO R4 INTERFACES
    r4_tgen1_num_intfs = 1
    r4_tgen1_intfs_alias = 'rtr2_tgen1_intf.1'
    r4_tgen1_speed = 'ether10000lan'

    # TGEN1 TO R5 INTERFACES
    r5_tgen1_num_intfs = 1
    r5_tgen1_intfs_alias = 'rtr3_tgen1_intf.1'
    r5_tgen1_speed = 'ether10000lan'

    tgen1_r1_num_intfs = 1
    tgen1_r1_intfs_alias = 'tgen1_rtr6_intf.1'

    tgen1_r4_num_intfs = 1
    tgen1_r4_intfs_alias = 'tgen1_rtr2_intf.1'

    tgen1_r5_num_intfs = 1
    tgen1_r5_intfs_alias = 'tgen1_rtr3_intf.1'

    # SCRIPT ARGUMENTS
    startup_config = 'harddisk:startup-config'
    routing_proto = 'isis'

    # FLAGS
    srv6_flag = True

    rsp_process_list = ['fib_mgr', 'mpls_io_ea', 'ifmgr', 'bfd', 'ipv6_ma',
                         'ipv6_rib', 'ipv6_acl_daemon']
    lc_process_list = ['fib_mgr', 'ifmgr', 'mpls_io_ea', 'ipv6_ea', 'ipv6_ma']

def main():
    """Segment routing script run"""
    run(testscript='/ws/mastarke-sjc/my_local_git/segment_routing/sr.py',
    uids=Or('common_setup',
            And('SanityTraffic'),
            And('SrLoopback'),
            And('SrFeatureInteraction'),
            And('Rsp_failover_fail_back'),
            And('Process_restarts_rsp'),
            And('Process_restarts_lc'),
            And('Lc_reload'),
            And('Remove_add_config_loopback'),
            And('Remove_add_config_igp'),
            And('Interface_flap_main_interface'),
            And('Interface_flap_bundle'),
            And('Interface_flap_bundle_members'),
            And('Bundle_add_remove_members'),
            And('Sr_Ecmp'),
            Not('.*'),
            'common_cleanup')
        )
