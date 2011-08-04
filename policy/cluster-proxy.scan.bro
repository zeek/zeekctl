# If scan is loaded, don't locally record ScanSummary events.
# this is special in the way that it is implemented, in that these
# events would be generated on a proxy.

redef notice_action_filters += {
        [ScanSummary] = ignore_notice,
};

