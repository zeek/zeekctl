##! Configuration for a worker cluster node used with BroControl.

@load base/frameworks/cluster

# Log rotation support.
redef Log::default_rotation_interval = 24 hrs;
redef Log::default_rotation_postprocessor_cmd = "delete-log";

## Record all packets into trace file.
## This will only be happen if the -w flag is given on the command line.
@load misc/trim-trace-file
redef record_all_packets = T;

