
# Enable default log rotation.

redef Log::default_rotation_interval = 1hrs;
redef Log::default_rotation_postprocessor = "archive-log";

event file_opened(f: file)
	{
	# Create a link from the archive directory to the newly created file.
	if ( ! bro_is_terminating() )
		system(fmt("create-link-for-log %s", get_file_name(f)));
	}
