# There are so many HTTP servers out there that this consumes too much memory.
redef ProtocolDetector::suppress_servers = { ANALYZER_HTTP };
