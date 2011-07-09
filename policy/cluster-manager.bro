# $Id: cluster-manager.bro 7098 2010-10-19 00:54:23Z robin $
#
# Cluster manager configuration.

@prefixes += cluster-manager

@load broctl
@load broctl/filter-duplicates
@load frameworks/notice
@load broctl/mail-alarms

## Set the mail script to be the default script for the cluster deployment.
redef Notice::mail_script = "mail-alarm";

## Set the template value that the mail script will use to send email.  The
## default mail-alarm script will replace the value.
redef Notice::mail_dest = "_broctl_default_";

# This grabs the remote peers (workers) and saves some status info
# to a local peer_status.log.
#@load save-peer-status

#redef FilterDuplicates::filters += {
#	[Drop::AddressSeenAgain] = FilterDuplicates::match_src,
#};
#