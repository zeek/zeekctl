##! Configuration for a standalone system used with BroControl.

@load standalone-layout

# Log rotation support.
redef Log::default_rotation_interval = 1 hrs;
redef Log::default_rotation_postprocessor_cmd = "archive-log";

# Record all packets into trace file.
# This will only be happen if the -w flag is given on the command line.
@load misc/trim-trace-file
redef record_all_packets = T;

