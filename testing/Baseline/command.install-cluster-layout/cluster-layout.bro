# Automatically generated. Do not edit.
redef Cluster::nodes = {
	["control"] = [$node_roles=set(Cluster::CONTROL), $ip=127.0.0.1, $zone_id="", $p=9999/tcp],
	["manager"] = [$node_roles=set(Cluster::MANAGER, Cluster::LOGNODE), $ip=127.0.0.1, $zone_id="", $p=10000/tcp, $workers=set("worker-1", "worker-2")],
	["datanode-1"] = [$node_roles=set(Cluster::DATANODE), $ip=127.0.0.1, $zone_id="", $p=10001/tcp, $manager="manager", $workers=set("worker-1", "worker-2")],
	["worker-1"] = [$node_roles=set(Cluster::WORKER), $ip=127.0.0.1, $zone_id="", $p=10002/tcp, $interface="eth0", $manager="manager", $datanode="datanode-1"],
	["worker-2"] = [$node_roles=set(Cluster::WORKER), $ip=127.0.0.1, $zone_id="", $p=10003/tcp, $interface="eth1", $manager="manager", $datanode="datanode-1"],
	["time-machine"] = [$node_roles=set(Cluster::TIME_MACHINE), $ip=192.168.0.11, $p=12345/tcp],
};
