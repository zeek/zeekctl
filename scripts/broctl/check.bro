##! This script contains tuning that's particular to running BroControl's
##! ``check`` command and is only loaded at that time.

redef Log::default_rotation_interval=0secs;

# When checking the configuration, Bro needs to exit after fully initializing.
event bro_init() &priority=-10
	{
	terminate_communication();
	}

