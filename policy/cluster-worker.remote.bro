# Remote config for cluster analysis WORKERS.

# Do not copy the worker's remote.log to the manager
redef Remote::rm_log &disable_print_hook;

# The worker initiates connection to manager and proxy, but need no events from them.
# (the manager and the proxy register for events from us workers)
redef Remote::destinations += {
	["manager"] = [$host=BroCtl::manager$ip,
		$p=BroCtl::manager$p,
		$events=BroCtl::manager_events,
		$connect=T, $sync=F, $retry=1mins,
		$class=BroCtl::workers[WORKER]$tag],

	["proxy"] = [$host=BroCtl::workers[WORKER]$proxy$ip,
		$p=BroCtl::workers[WORKER]$proxy$p,
		$connect=T, $sync=T, $retry=1mins,
		$class="proxy"],

	["update"] = [$host=BroCtl::manager$ip,
		$events=BroCtl::update_events,
		$sync=F,
		$class="update"]
	};

