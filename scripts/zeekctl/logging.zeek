##! Zeekctl specific script for placing a .log_suffix file and setting the
##! LOG_SUFFIX environment variable for the default rotation postprocessor
##! when multiple loggers are configured. This is used by post-terminate
##! and make-archive-name to distinguish logs from different loggers.
##!
@load base/frameworks/cluster

module Control;

global log_suffix_filename = ".log_suffix";

@if ( Cluster::local_node_type() == Cluster::LOGGER )
event zeek_init()
	{
	local logger_count = 0;
	for ( _, n in Cluster::nodes )
		{
		if ( n$node_type == Cluster::LOGGER )
			++logger_count;
		}

	if ( logger_count > 1 )
		{
		# 1) Set the environment variable for the archive-log / make-archive-name
		#    pipeline.
		Log::default_rotation_postprocessor_cmd_env["LOG_SUFFIX"] = Cluster::node;

		# 2) Create the .log_suffix file within the logger's working directory.
		local f = open(log_suffix_filename);
		if ( ! active_file(f) )
			{
			Reporter::error(fmt("failed to open %s", log_suffix_filename));
			return;
			}

		if ( ! write_file(f, fmt("%s\n", Cluster::node)) )
			Reporter::error(fmt("failed to write %s", log_suffix_filename));

		close(f);
		}
	else
		{
		# When running a single logger config, cleanup any leftover suffix
		# suffix files that may linger around. Otherwise, this is a noop.
		if ( file_size(log_suffix_filename) >= 0 )
			unlink(log_suffix_filename);
		}
	}
@endif
