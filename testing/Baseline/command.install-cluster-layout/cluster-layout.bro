# Automatically generated. Do not edit.
redef Cluster::nodes = {
	["control"] = [$node_type=Cluster::CONTROL, $ip=127.0.0.1, $zone_id="", $p=47760/tcp],
	["manager"] = [$node_type=Cluster::MANAGER, $ip=127.0.0.1, $zone_id="", $p=47761/tcp, $workers=set( "worker-1" , "worker-2" )],
	["proxy-1"] = [$node_type=Cluster::PROXY, $ip=127.0.0.1, $zone_id="", $p=47762/tcp, $manager="manager", $workers=set( "worker-1" , "worker-2" )],
	["worker-1"] = [$node_type=Cluster::WORKER, $ip=127.0.0.1, $zone_id="", $p=47763/tcp, $interface="eth0", $manager="manager", $proxy="proxy-1"],
	["worker-2"] = [$node_type=Cluster::WORKER, $ip=127.0.0.1, $zone_id="", $p=47764/tcp, $interface="eth1", $manager="manager", $proxy="proxy-1"],
	["time-machine"] = [$node_type=Cluster::TIME_MACHINE, $ip=192.168.0.11, $p=12345/tcp],
};
