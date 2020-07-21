##! This script contains tuning that's particular to running ZeekControl's
##! ``check`` and ``scripts`` commands and is only loaded at those times.

redef Log::default_rotation_interval=0secs;

# When checking the configuration, Zeek needs to exit after fully initializing.
event zeek_init() &priority=-10
	{
	terminate();
	}

# We want the local loaded_scripts.log on all nodes (not just on the node that
# does the logging).
event zeek_init() &priority=-10
    {
    local f = Log::get_filter(LoadedScripts::LOG, "default");
    f$log_local = T;
    Log::remove_filter(LoadedScripts::LOG, "default");
    Log::add_filter(LoadedScripts::LOG, f);
    }

# This prevents "zeekctl scripts" from hanging.
redef exit_only_after_terminate = F;
# This prevents us from trying to read the current global databases (which might be
# locked) during a check.
redef Broker::table_store_db_directory = ".";
