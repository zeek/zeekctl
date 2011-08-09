##! Configuration for a proxy cluster node used with BroControl.

@load base/frameworks/cluster

# Log rotation support.
redef Log::default_rotation_interval = 24 hrs;
redef Log::default_rotation_postprocessor_cmd = "delete-log";
