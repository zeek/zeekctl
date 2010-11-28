# $Id: broctl-check.bro 7098 2010-10-19 00:54:23Z robin $
#
# Only loaded when checking configuration, not when running live.

redef RotateLogs::rotate_on_shutdown = F;
		
