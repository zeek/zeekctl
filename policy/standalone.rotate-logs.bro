# $Id: standalone.rotate-logs.bro 7098 2010-10-19 00:54:23Z robin $

redef log_rotate_interval = 24hrs;
redef log_rotate_base_time = "0:00";
redef RotateLogs::default_postprocessor = "archive-log";
