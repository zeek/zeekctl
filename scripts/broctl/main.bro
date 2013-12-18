# Load the script to support the "scripts" command.
@load misc/loaded-scripts

# All cluster nodes are inherently controllable with BroControl.
# TODO: This kind of sucks right now though because it always causes the
#       communications framework to hold open a port which can cause
#       high CPU usage on lightly loaded links due to the core packet
#       extraction loop.
@load frameworks/control/controllee

## All nodes allow remote control from loopback.  This solves an occasional
## problem in some all-local installations.
redef Communication::nodes += {
	# We're waiting for connections from this host for control.
	["local-control"] = [$host=127.0.0.1, $class="control", $events=Control::controller_events],
};

## Reconfigure the reporter framework to stop printing to STDERR
## because STDERR is redirected and not normally visible when through
## BroControl.  The logs will still be available through the normal
## reporter stream in the logging framework.
redef Reporter::warnings_to_stderr = F;
redef Reporter::errors_to_stderr = F;
