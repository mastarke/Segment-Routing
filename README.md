##############################################
# Segment Routing Automation
##############################################
<br />
<br />
<br />


1. Explanation of YAML file alias.


   YAML file will require adding the alias in order to map the router interface
   in the script.<br />
   This is used in the job file to ensure you can easily get
   the interface you wish.

    EXAMPLE of YAML FILE:


    topology:
        R6:
            interfaces:
            #rtr6 to rtr4 interfaces
                tenGigE0/0/0/0/2:
                    alias: rtr6_rtr4_intf.1
                    speed: ether10000
                    link_type: physical
                    peer:
                    - R4::tengigE0/2/0/10
                    type: unkown

<br />
<br />

Mapping YAML file to Job file. It's in the job file where you will tell how many
interfaces to grab from YAML file via 'r1_r2_num_intfs' argument. The 'r1_r2_intfs_alias'
argument is used to tell where to start grabbing interfaces from.


    class SrScriptArgs(object):
        """ Segment routing script aruguments."""

        testbed_file = ('/nobackup/mastarke/my_local_git/'
                    'segment_routing/sr-vpls.yaml')
        uut_list = ['R6', 'R4', 'R7', 'R2', 'R3']


        # INTERFACE ARGUMENTS TO SELECT LINKS IN COMMON SETUP
        # R1 TO R2 INTERFACES
        r1_r2_num_intfs = 3 <--- used to tell number of interfaces needed to script
        r1_r2_intfs_alias = 'rtr6_rtr4_intf.1' <--- Maps to Yaml alias



2. Test cases automated.<br />

    #########################<br />
    Feature - SR VPLS<br />
    #########################<br />
    <br />
        1. Verify broadcast traffic over VPLS on SRTE tunnels (Automated)<br />
        2. Verify multicast traffic over VPLS on SRTE tunnels (Automated)<br />
        3. Verify unknown unicast traffic over VPLS on SRTE tunnels (Automated)<br />
        4. Add one more host connecting the PE. Verify local switching (Automated)<br />
        5. Add one more host to PE and verify remote switching (Automated)<br />
        6. Add a new PE, and verify BUM and unicast traffic (Automated)<br />
        7. delete one more host connecting the PE. Verify local switching (Automated)<br />
        8. delete one more host to PE and verify remote switching (Automated)<br />
        9. delete a new PE, and verify BUM and unicast traffic (Automated)<br />
        10. Switch between SRTE and RSVP TE tunnels and vice versa. Verify traffic (Automated)<br />
        11. Verify VPLS traffic over SRTE tunnels for all flavors of path option dynamic segment routing (Automated)<br />
        12. Verify VPLS traffic over SRTE tunnels for all flavors of path option  segment routing (Automated)<br />
        13. Verify VPLS traffic over SRTE tunnels for all flavors of explicit path option  segment routing (Automated)<br />
        14. Verify VPLS traffic forwarding over Bundle (Automated)<br />
        15. Verify VPLS traffic forwarding over Bundle sub interface (Not automated)<br />
        16. Verify VPLS traffic forwarding over physical interface (Automated)<br />
        17. Verify VPLS traffic forwarding over physical sub interface (Automated)<br />
        18. Add a bundle member from a different LC to existing bundle (Automated)<br />
        19. VPLS over ECMP SRTE tunnels (Adding case)<br />
        20. VPLS over SRTE tunnels with ECMP IGP paths (IGP ECMP not supported)<br />
        21. 64 ECMP tunnel paths (Adding case)<br />
        22. 64 IGP paths (IGP ECMP not supported)<br />
        23. shutdown AC interface (Automated)<br />
        24. Remove a bundle member link down to zero (Automated)<br />
        25. bring down IGP ECMP paths all the way down to zero and up (Automated)<br />
        26. bring down tunnel ECMP paths all the way  down to zero and up (Adding case)<br />
        27. RSPFO (Automated)<br />
        28. process restart (ISIS, OSPF, l2vpn_mgr, fib_mgr) (Automated)<br />
        29. switch between startup config and full cofig and vice versa (Automated)<br />
        30. load startup config and commit replace (Automated)<br />
        31. Reload the LC which has primary interface (Automated)<br />
        32. LC OIR (Not automated)<br />
        33. RSP OIR (Not automated)<br />
        34. Reload Chassis (Not automated)<br />
        35. pyhical link flap (Automated)<br />
        36. Remove and add VPLS config (Automated)<br />
        37. Remove and add IGP config (Automated)<br />
        38. Verify TI-LFA protection for VPLS traffic over SR TE tunnels (Automated)<br />
        39. Verif TI-LFA protection for VPLS traffic for P and Q single labels (Not automated)<br />
        40. Verif TI-LFA protection for VPLS traffic for P and Q different labels (not automated)<br />
        41. Verify TI-LFA link protection for VPLS traffic(Not automated)<br />
        42. Verify TI-LFA node protection for VPLS traffic (Automated)<br />
        43. Verify TI-LFA SRLG protection for VPLS traffic (Not automated)<br />
        44. Verify All the above cases with OSPF as IGP (Automated)<br />
        45. verify vpls traffic over SRTE tunnels with OSPF as IGP (Automated)<br />
        46. verify vpls traffic over SRTE tunnels with ISIS as IGP (Automated)<br />
        47. veirfy 3107 vpls traffic over SRTE tunnels (Not automated)<br />
        48. Verify traffic over VPLS PW established with BGP Auto discovery (Not automated)<br />
        49. Verify Demand Matrix stats for SRTE tunnels (Automated)<br />
        50. verify feature with line rate traffic (Automated)<br />
        51. verify feature on typhoon (Automated)<br />
        52. change tunnel physical path to various physical path with various path distance to tunnel dst (Automated)<br />
        53. memory leak check with pam tool (Automated)<br />
        54. remove / add l2vpn config (Automated)<br />
        55. remove/ add mpls ldp config (Automated)<br />
        56. remove / add mpls traffic-eng config (Automated)<br />
        57. vpls over sr with preferred path (Automated)<br />
        58. vpls over sr using control word (Automated)<br />
        59. vlps over sr-te using flow label (Automated)<br />
        60. verify vpls over sr-te with forward-class on tunnel (FWD class not supported)<br />
<br />
<br />
        Total automation 48 out of 60<br />
        <br />
    #########################<br />
    Feature - SRv6<br />
    #########################<br />
<br />
    1. Verify SRv6 Prefix SID can be configured on Loopback interface (Automated)<br />
    2. Verify multiple SRv6 address can be configured under the loopback interface (Automated)<br />
    3. Verify multiple loopbacks can have SRv6 SID (Automated)<br />
    4. Verify SRv6 Prefix SID config can be removed (Automated)<br />
    5. Verify SRv6 config rollback (Automated)<br />
    6. Switch between startup-config and full SRv6 config. Verify the functionality (Automated)<br />
    7. Verify removing and adding loopback interface config (Automated)<br />
    8. Verify RIB/FIB show command for SRv6 (Automated)<br />
    9. Verify PD flags for SRv6 in "show cef ipv6 hardware location <> detail" (Automated)<br />
    10. Verify all cli & show commands on cXR and eXR (Automated)<br />
    11. Verify SRv6 capable node inspects SRH header only if DA is forus address (Automated)<br />
    12. Verify SRH header processing is done for local-sid match only (Automated)<br />
    13. Verify segments left is decremented every SRv6 hop (Automated)<br />
    14. Verify DA is updated by every SRv6 end node (Automated)<br />
    15. Verify end to end traffic forwarding happens as decided by SRH header (Automated)<br />
    16. Verify SR end point functionality on cXR and eXR nodes (Automated)<br />
    17. Verify Transit node is not inspecting SRH header (Automated)<br />
    18. Verify Transit node is not updating SRH header (Automated)<br />
    19. Verify transit node does ECMP based on flow label (with SRH header present in v6 packet) (Not automated)<br />
    20. Verify ACL can be used to match SA or DA even if v6 packet is carrying SRH header (Automated)<br />
    21. Verify counters for ACL when v6 packet is carrying SRH header (Automated)<br />
    22. Verify if DA!= IPv6 SID (local) and SRH header is present then traffic is dropped (Automated)<br />
    23. Verify uRPF on v6 source when v6 packet is carrying SRH header (Not automated)<br />
    24. Verify Sec-06 as per requirements mentioned in function spec (Not automated)<br />
    25. Verify SRv6 traffic upto 10 SRv6 SIDs in the SRH header (Automated)<br />
    26. Verify Ping and Tracert for IPv6 SID (Automated)<br />
    27. Verify BGP ipv6 sessions over SRv6 SID between two nodes (Automated)<br />
    28. Verify SRv6 traffic can be forwarded over RSVP-TE tunnel (Not supported)<br />
    29. Verify SRv6 traffic can be forwarded over SR-TE tunnel (Not supported)<br />
    30. Verify MPLS prefix sid can be allocated for SRv6 SID and verify traffic forwarding (Automated)<br />
    31. Verify SRv6 traffic forwarding on Bundle interface (Automated)<br />
    32. Verify SRv6 traffic forwarding over bundle sub interface (Not automated)<br />
    33. Verify SRv6 traffic forwarding over physical interface (Automated)<br />
    34. Verify SRv6 traffic forwarding over physical sub interface (Automated)<br />
    35. Verify SRv6 prefix sid cant be assigned if the interface is already in vrf (Not automated)<br />
    36. Verify SRv6 traffic forwarding on GRE interface (Not supported 621)<br />
    37. Reload LC (Automated)<br />
    38. shut and no shut interface (Automated)<br />
    39. process restart ipv6_ma, ipv6_rib,fib_mgr,lsd,isis, (Automated)<br />
    40. RSP FO (Automated)<br />
    41. Remove add isis config (Automated)<br />
    42. Verify Scaled number of SRv6 SID(1000) that the router can take (Automated)<br />
    43. Verify traffic is sent to large number of SRv6 SIDs, add and remove SRv6 SID configuration (Automated)<br />
    44. Verify FO/FB with large scale SRv6 SIDs while traffic is present (Not automated)<br />
    45. Verify ACL can be configured which can permit or deny a range of extension header values (Automated)<br />
    46. Verify that ACL can match against an extension header or range of extension header even if this extension header is not directly underneath the ipv6 header (Automated)<br />
    47. Verify IPv6 ACL process restart (IPv6_acl, IPv6_acl_deamon) (Automated)<br />
    48. Check memory leak by marking and un-marking for-us prefix SID (Automated)<br />
    49. A forus prefix transition to SRv6 and vice versa (Automated)<br />
    50. Shut/no shut the SRv6 prefix next hop interface (Automated)<br />
    51. Verify Flex-CLI for SRv6 prefix SID (Not automated)<br />
    52. Verify XML show o/p SRv6 flags for RIB and CEF show commands (Not automated)<br />
    53. Verify two same ipv6 prefix-sid is not assigned to two different loopback address (Not automated)<br />
    54. Verify "show arm ipv6 conflicts" displays duplicate SRv6 prefix-SIDs (Not automated)<br />
<br />
<br />
        Total automation 41 out of 54<br />
        <br />
