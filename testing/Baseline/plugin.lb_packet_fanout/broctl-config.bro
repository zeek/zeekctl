# Automatically generated. Do not edit.
redef Notice::mail_dest = "root@localhost";
redef Notice::mail_dest_pretty_printed = "root@localhost";
redef Notice::sendmail  = "/usr/sbin/sendmail";
redef Notice::mail_subject_prefix  = "[Bro]";
redef Notice::mail_from  = "Big Brother <bro@gras-desktop.cern.ch>";
@if ( Cluster::local_node_type() == Cluster::MANAGER )
redef Log::default_rotation_interval = 3600 secs;
redef Log::default_mail_alarms_interval = 86400 secs;
@endif
redef Communication::listen_ipv6 = T ;
redef Pcap::snaplen = 8192;
redef Pcap::bufsize = 128;
redef Pcap::packet_fanout_enable = T;
redef Pcap::packet_fanout_id = 0;
redef Pcap::packet_fanout_defrag = T;
