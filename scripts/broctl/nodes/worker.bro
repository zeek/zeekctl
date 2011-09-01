##! Configuration for a worker cluster node used with BroControl.

@load base/frameworks/cluster

## Record all packets into trace file.
## This will only be happen if the -w flag is given on the command line.
@load misc/trim-trace-file
redef record_all_packets = T;

# Log rotation support.
redef Log::default_rotation_interval = 24 hrs;
redef Log::default_rotation_postprocessor_cmd = "delete-log";

### The cluster manager will inform us with these events if it's interested in
### further connection attempts from that source.
#global watch_addr_table: set[addr] &read_expire=7days &persistent;
#
#global address_seen_again: event(a: addr);
#
#event Drop::address_restored(a: addr)
#	{
#	debug_log(fmt("received restored for %s", a));
#	add watch_addr_table[a];
#	}
#
#event Drop::address_dropped(a: addr)
#	{
#	debug_log(fmt("received dropped for %s", a));
#	delete watch_addr_table[a];
#	}
#
#event Drop::address_cleared(a: addr)
#	{
#	debug_log(fmt("received cleared for %s", a));
#	delete watch_addr_table[a];
#	}
#
## We need to forward the new connection attempt.
#event new_connection(c: connection)
#	{
#	local a = c$id$orig_h;
#	if ( a in watch_addr_table )
#		{
#		debug_log(fmt("sending seen_again for %s", a));
#		event Drop::address_seen_again(a);
#		delete watch_addr_table[a];
#		}
#	}


