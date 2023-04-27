# @TEST-IGNORE
#
# Script creating a much-logging.log. Each node is producing 5 log entries
# per second by default, so they should fill up quickly.

@load base/frameworks/logging
@load base/frameworks/cluster

module MuchLogging;

export {
	redef enum Log::ID += { LOG };

	type Info: record {
		ts: time &log;
		id: count &log;
		node: string &default=Cluster::node;
	};

	option log_interval: interval = 0.2sec;
}

event tick(id: count)
	{
	Log::write(LOG, [$ts=network_time(), $id=id]);
	schedule log_interval { tick(++id) };
	}

event zeek_init()
	{
	Log::create_stream(LOG, [$columns=Info, $path="much-logging"]);
	schedule log_interval { tick(1) };
	}
