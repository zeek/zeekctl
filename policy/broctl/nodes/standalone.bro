##! Configuration for a standalone system used with BroControl.

@load standalone-layout
@load frameworks/notice

## Record all packets into trace file.
## This will only be happen if the -w flag is given on the command line.
@load misc/trim-trace-file
redef record_all_packets = T;

redef Log::default_rotation_interval = 1hrs;
redef Log::default_rotation_postprocessor = "archive-log";

event file_opened(f: file)
	{
	# Create a link from the archive directory to the newly created file.
	if ( ! bro_is_terminating() )
		system(fmt("create-link-for-log %s", get_file_name(f)));
	}
