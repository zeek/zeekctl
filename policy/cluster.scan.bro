# $Id: cluster.scan.bro 7098 2010-10-19 00:54:23Z robin $

redef addr_scan_trigger = 3;  
redef ignore_scanners_threshold = 500; 

redef pre_distinct_peers &read_expire = 12hrs;

redef distinct_backscatter_peers &create_expire = 5hrs;
redef distinct_peers &create_expire = 5hrs;
redef distinct_ports &create_expire = 5hrs;
redef distinct_low_ports &create_expire = 5hrs;
redef possible_scan_sources &create_expire = 5hrs;

