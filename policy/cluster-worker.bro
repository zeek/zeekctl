##! This is the cluster WORKER top-level policy for configuration settings that are 
##! common to all worker node (as everything currently is except setting WORKER id).

@prefixes += cluster-worker

@load broctl
@load broctl/trim-trace-file
@load frameworks/cluster

@load support/remote/analysis-groups
