##! Configuration for a standalone system used with BroControl.

@load standalone-layout
@load frameworks/notice

## Record all packets into trace file.
## This will only be happen if the -w flag is given on the command line.
@load misc/trim-trace-file
redef record_all_packets = T;
