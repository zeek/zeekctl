redef log_rotate_interval = 24 hrs;
redef log_rotate_base_time = "0:00";
redef RotateLogs::default_postprocessor = "delete-log";
