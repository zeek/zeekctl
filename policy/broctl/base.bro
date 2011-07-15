
@load site

# All cluster nodes are inherently controllable
# TODO: This kind of sucks right now though because it always causes the
#       communications framework to hold open a port which can cause 
#       high CPU usage on lightly loaded links due to the core packet
#       extraction loop.
@load frameworks/control/controllee

# All nodes allow remote control from loopback.  This solves an occasional
# problem in some all local installations.
redef Communication::nodes += {
	# We're waiting for connections from this host for control.
	["local-control"] = [$host=127.0.0.1, $class="control", $events=Control::controller_events],
};

#@load misc/analysis-policy

# Auto generated file.
@load local-networks
