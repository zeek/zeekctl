##! This script contains tuning that's particular to running ZeekControl's
##! ``process-trace`` command and is only loaded at that time.

redef Log::default_rotation_interval=0secs;

redef Log::enable_local_logging = T;
