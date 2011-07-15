## Configuration for a standalone system.

@load broctl/mail-alarms
@load broctl/trim-trace-file

@load standalone-layout

redef MailAlarms::output &rotate_interval = 12hrs;

# Record all packets into trace file.
redef record_all_packets = T;

#redef mail_script = "mail-alarm";
#redef mail_dest = "_broctl_default_"; # Will be replaced by mail script.

redef log_rotate_interval = 1hrs;
redef log_rotate_base_time = "0:00";
#redef RotateLogs::default_postprocessor = "archive-log";

event file_opened(f: file)
	{
	# Create a link from the archive directory to the newly created file.
	if ( ! bro_is_terminating() )
		system(fmt("create-link-for-log %s", get_file_name(f)));
	}
