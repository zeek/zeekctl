# Configuration options.
#

class Option:
    # Options category.
    USER = 1       # Standard user-configurable option.
    INTERNAL = 2   # internal, don't expose to user.
    AUTOMATIC = 3  # Set automatically, unlikely to be changed.

    def __init__(self, name, default, type, category, dontinit, description, legacy_name=None):
        self.name = name
        self.default = default
        self.type = type
        self.category = category
        self.dontinit = dontinit
        self.description = description
        self.legacy_name = legacy_name

        if type == "string":
            if not isinstance(default, str):
                raise ValueError("option '%s' default value must be string" % name)
        else:
            if not isinstance(default, int):
                raise ValueError("option '%s' default value must be int" % name)


options = [
    # User options.
    Option("Debug", 0, "bool", Option.USER, False,
           "Enable extensive debugging output in spool/debug.log."),

    Option("HaveNFS", 0, "bool", Option.USER, False,
           "True if shared files are mounted across all nodes via NFS (see the FAQ_)."),
    Option("SaveTraces", 0, "bool", Option.USER, False,
           "True to let backends capture short-term traces via '-w'. These are not archived but might be helpful for debugging."),

    Option("StopTimeout", 60, "int", Option.USER, False,
           "The number of seconds to wait before sending a SIGKILL to a node which was previously issued the 'stop' command but did not terminate gracefully."),
    Option("CommTimeout", 10, "int", Option.USER, False,
           "The number of seconds to wait before assuming Broker communication events have timed out."),
    Option("ControlTopic", "zeek/control", "string", Option.USER, False,
           "The Broker topic name used for sending and receiving control messages to Zeek processes."),
    Option("CommandTimeout", 60, "int", Option.USER, False,
           "The number of seconds to wait for a command to return results."),
    Option("ZeekPort", 27760, "int", Option.USER, False,
           "The TCP port number that Zeek will listen on. For a cluster configuration, each node in the cluster will automatically be assigned a subsequent port to listen on.", "BroPort"),
    Option("LogRotationInterval", 3600, "int", Option.USER, False,
           "The frequency of log rotation in seconds for the manager/standalone node (zero to disable rotation). This overrides the Zeek script variable Log::default_rotation_interval."),
    Option("LogDir", "${ZeekBase}/logs", "string", Option.USER, False,
           "Directory for archived log files."),
    Option("MakeArchiveName", "${ZeekBase}/share/zeekctl/scripts/make-archive-name", "string", Option.USER, False,
           "Script to generate filenames for archived log files."),
    Option("CompressLogs", 1, "bool", Option.USER, False,
           "True to compress archived log files."),
    Option("CompressLogsInFlight", 0, "int", Option.USER, False,
           "Set to greater than zero to compress archived log files as they're created instead of during rotation.  The value indicates the compression level to use between 1 and 9 (values of 6 or 7 are a typical choice to bias slightly more towards better compression at cost of performance). If this is enabled, the CompressLogs, and CompressCmd arguments will be ignored as the files are compressed automatically by Zeek."),
    Option("CompressCmd", "gzip", "string", Option.USER, False,
           "If archived logs will be compressed, the command to use for that. The specified command must compress its standard input to standard output."),
    Option("CompressExtension", "gz", "string", Option.USER, False,
           "If archived logs will be compressed, the file extension to use on compressed log files. When specifying a file extension, don't include the period character (e.g., specify 'gz' instead of '.gz')."),
    Option("PrivateAddressSpaceIsLocal", 1, "bool", Option.USER, False,
           "Whether Zeek should automatically consider private address ranges local. Mirrors Site::private_address_space_is_local in Zeek. On by default."),

    Option("SendMail", "@SENDMAIL@", "string", Option.USER, False,
           "Location of the sendmail binary.  Make this string blank to prevent email from being sent. The default value is configuration-dependent and determined automatically by CMake at configure-time. This overrides the Zeek script variable Notice::sendmail."),
    Option("MailSubjectPrefix", "[Zeek]", "string", Option.USER, False,
           "General Subject prefix for mails. This overrides the Zeek script variable Notice::mail_subject_prefix."),

    Option("MailReplyTo", "", "string", Option.USER, False,
           "Reply-to address for zeekctl-generated mails."),
    Option("MailTo", "<user>", "string", Option.USER, True,
           "Destination address for non-alarm mails. This overrides the Zeek script variable Notice::mail_dest."),
    Option("MailFrom", "Zeek <zeek@localhost>", "string", Option.USER, True,
           "Originator address for mails. This overrides the Zeek script variable Notice::mail_from."),

    Option("MailAlarmsTo", "${MailTo}", "string", Option.USER, True,
           "Destination address for alarm summary mails. Default is to use the same address as MailTo. This overrides the Zeek script variable Notice::mail_dest_pretty_printed."),
    Option("MailAlarmsInterval", 86400, "int", Option.USER, False,
           "The frequency (in seconds) of sending alarm summary mails (zero to disable). This overrides the Zeek script variable Log::default_mail_alarms_interval."),

    Option("MailConnectionSummary", 1, "bool", Option.USER, False,
           "True to mail connection summary reports each log rotation interval (if false, then connection summary reports will still be generated and archived, but they will not be mailed). However, this option has no effect if the trace-summary script is not available."),
    Option("MailHostUpDown", 1, "bool", Option.USER, False,
           "True to enable sending mail when zeekctl cron notices the availability of a host in the cluster to have changed."),
    Option("MailArchiveLogFail", 1, "bool", Option.USER, False,
           "True to enable sending mail when log files fail to be archived."),
    Option("MailReceivingPackets", 1, "bool", Option.USER, False,
           "True to enable sending mail when zeekctl cron notices that an interface is not receiving any packets (note that such mail is not sent when StatsLogEnable is 0)."),

    Option("MinDiskSpace", 5, "int", Option.USER, False,
           "Minimum percentage of disk space available before zeekctl cron mails a warning.  If this value is 0, then no warning will be sent."),
    Option("StatsLogEnable", 1, "bool", Option.USER, False,
           "True to enable ZeekControl to write statistics to the stats.log file."),
    Option("StatsLogExpireInterval", 0, "int", Option.USER, False,
           "Number of days entries in the stats.log file are kept (zero means never expire)."),
    Option("CrashExpireInterval", 0, "int", Option.USER, False,
           "Number of days that crash directories are kept (zero means never expire)."),
    Option("LogExpireInterval", "0", "string", Option.USER, False,
           "Time interval that archived log files are kept (a value of 0 means log files never expire).  The time interval is expressed as an integer followed by one of the following time units: day, hr, min."),
    Option("KeepLogs", "", "string", Option.USER, False,
           "A space-separated list of filename shell patterns of expired log files to keep (empty string means don't keep any expired log files). The filename shell patterns are not regular expressions and do not include any directories. For example, specifying 'conn.* dns*' will prevent any expired log files with filenames starting with 'conn.' or 'dns' from being removed. Finally, note that this option is ignored if log files never expire."),
    Option("ZeekArgs", "", "string", Option.USER, False,
           'Additional arguments to pass to Zeek on the command-line (e.g. zeekargs=-f "tcp port 80").', "BroArgs"),
    Option("MemLimit", "unlimited", "string", Option.USER, False,
           "Maximum amount of memory for Zeek processes to use (in KB, or the string 'unlimited')."),
    Option("Env_Vars", "", "string", Option.USER, False,
           "A comma-separated list of environment variables (e.g. env_vars=VAR1=123, VAR2=456) to set on all nodes immediately before starting Zeek.  Node-specific values (specified in the node configuration file) override these global values."),

    Option("TimeFmt", "%d %b %H:%M:%S", "string", Option.USER, False,
           "Format string to print date/time specifications (see 'man strftime')."),

    Option("Prefixes", "local", "string", Option.USER, False,
           "Additional script prefixes for Zeek, separated by colons. Use this instead of @prefix."),

    Option("SitePolicyScripts", "local.zeek", "string", Option.USER, False,
           "Space-separated list of local policy files that will be automatically loaded for all Zeek instances.  Scripts listed here do not need to be explicitly loaded from any other policy scripts."),

    Option("StatusCmdShowAll", 0, "bool", Option.USER, False,
           "True to have the status command show all output, or False to show only some of the output (peer information will not be collected or shown, so the command will run faster)."),
    Option("StopWait", 0, "bool", Option.USER, False,
           "True to force the stop command to wait for the post-terminate script to finish, or False to let post-terminate finish in the background."),

    Option("CronCmd", "", "string", Option.USER, False,
           "A custom command to run everytime the cron command has finished."),

    Option("PFRINGClusterID", 21, "int", Option.USER, False,
           "If PF_RING flow-based load balancing is desired, this is where the PF_RING cluster id is defined.  In order to use PF_RING, the value of this option must be non-zero."),
    Option("PFRINGClusterType", "4-tuple", "string", Option.USER, False,
           "If PF_RING flow-based load balancing is desired, this is where the PF_RING cluster type is defined.  Allowed values are: 2-tuple, 4-tuple, 5-tuple, tcp-5-tuple, 6-tuple, inner-2-tuple, inner-4-tuple, inner-5-tuple, inner-tcp-5-tuple, or inner-6-tuple.  Zeek must be linked with PF_RING's libpcap wrapper and PFRINGClusterID must be non-zero for this option to work."),
    Option("PFRINGFirstAppInstance", 0, "int", Option.USER, False,
           "The first application instance for a PF_RING dnacluster interface to use.  Zeekctl will start at this application instance number and increment for each new process running on that DNA cluster.  Zeek must be linked with PF_RING's libpcap wrapper, PFRINGClusterID must be non-zero, and you must be using PF_RING+DNA and libzero for this option to work."),

    Option("PcapSnaplen", 9216, "int", Option.AUTOMATIC, False,
           "Number of bytes per packet to capture from live interfaces via libpcap."),
    Option("PcapBufsize", 128, "int", Option.AUTOMATIC, False,
           "Number of Mbytes to provide as buffer space when capturing from live interfaces via libpcap."),

    Option("TimeMachineHost", "", "string", Option.USER, False,
           "If the manager should connect to a Time Machine, the address of the host it is running on."),
    Option("TimeMachinePort", "47757/tcp", "string", Option.USER, False,
           "If the manager should connect to a Time Machine, the port it is running on (in Zeek syntax, e.g., 47757/tcp)."),

    # Automatically set.
    Option("ZeekBase", "", "string", Option.AUTOMATIC, True,
           "Base path of zeekctl installation on all nodes.", "BroBase"),
    Option("Version", "", "string", Option.AUTOMATIC, True,
           "Version of the zeekctl."),
    Option("StandAlone", 0, "bool", Option.AUTOMATIC, True,
           "True if running in stand-alone mode (see elsewhere)."),
    Option("OS", "", "string", Option.AUTOMATIC, True,
           "Name of operating system as reported by uname."),
    Option("Time", "", "string", Option.AUTOMATIC, True,
           "Path to time binary."),
    Option("LogExpireMinutes", 0, "int", Option.AUTOMATIC, True,
           "Time interval (in minutes) that archived log files are kept (0 means they never expire).  Users should never modify this value (see the LogExpireInterval option)."),

    Option("BinDir", "${ZeekBase}/bin", "string", Option.AUTOMATIC, False,
           "Directory for executable files."),
    Option("Zeek", "${BinDir}/zeek", "string", Option.AUTOMATIC, False,
           "Path to Zeek binary.", "Bro"),
    Option("ScriptsDir", "${ZeekBase}/share/zeekctl/scripts", "string", Option.AUTOMATIC, False,
           "Directory for executable scripts shipping as part of zeekctl."),
    Option("PostProcDir", "${ZeekBase}/share/zeekctl/scripts/postprocessors", "string", Option.AUTOMATIC, False,
           "Directory for log postprocessors."),
    Option("HelperDir", "${ZeekBase}/share/zeekctl/scripts/helpers", "string", Option.AUTOMATIC, False,
           "Directory for zeekctl helper scripts."),
    Option("CfgDir", "${ZeekBase}/etc", "string", Option.AUTOMATIC, False,
           "Directory for configuration files."),
    Option("SpoolDir", "${ZeekBase}/spool", "string", Option.AUTOMATIC, False,
           "Directory for run-time data."),
    Option("BrokerDBDir", "${ZeekBase}/spool/brokerstore", "string", Option.AUTOMATIC, False,
           "Directory for data stores of persistent Broker-backed tables."),
    Option("PolicyDir", "${ZeekScriptDir}", "string", Option.AUTOMATIC, False,
           "Directory for standard policy files."),
    Option("StaticDir", "${ZeekBase}/share/zeekctl", "string", Option.AUTOMATIC, False,
           "Directory for static, arch-independent files."),

    Option("LibDir", "", "string", Option.AUTOMATIC, False,
           "Directory for library files."),
    # XXX Do we still need the following? --cpk
    Option("LibDir64", "${ZeekBase}/lib64", "string", Option.AUTOMATIC, False,
           "Directory for 64-bit architecture library files."),
    Option("LibDirInternal", "", "string", Option.AUTOMATIC, False,
           "Directory for ZeekControl's Python module."),
    Option("TmpDir", "${SpoolDir}/tmp", "string", Option.AUTOMATIC, False,
           "Directory for temporary data."),
    Option("TmpExecDir", "${SpoolDir}/tmp", "string", Option.AUTOMATIC, False,
           "Directory where binaries are copied before execution.  This option is ignored if HaveNFS is 0."),
    Option("StatsDir", "${LogDir}/stats", "string", Option.AUTOMATIC, False,
           "Directory where statistics are kept."),
    Option("PluginDir", "${LibDirInternal}/zeekctl/plugins", "string", Option.AUTOMATIC, False,
           "Directory where standard zeekctl plugins are located."),
    Option("PluginZeekDir", "${LibDir}/zeek/plugins", "string", Option.AUTOMATIC, False,
           "Directory where Zeek plugins are located.  ZeekControl will search this directory tree for zeekctl plugins that are provided by any Zeek plugin.", "PluginBroDir"),

    Option("TraceSummary", "${bindir}/trace-summary", "string", Option.AUTOMATIC, False,
           "Path to trace-summary script (empty if not available). Make this string blank to disable the connection summary reports."),
    Option("CapstatsPath", "${bindir}/capstats", "string", Option.AUTOMATIC, False,
           "Path to capstats binary; empty if not available."),

    Option("NodeCfg", "${CfgDir}/node.cfg", "string", Option.AUTOMATIC, False,
           "Node configuration file."),
    Option("LocalNetsCfg", "${CfgDir}/networks.cfg", "string", Option.AUTOMATIC, False,
           "File defining the local networks."),
    Option("StateFile", "${SpoolDir}/state.db", "string", Option.AUTOMATIC, False,
           "File storing the current zeekctl state."),
    Option("LockFile", "${SpoolDir}/lock", "string", Option.AUTOMATIC, False,
           "Lock file preventing concurrent shell operations."),

    Option("DebugLog", "${SpoolDir}/debug.log", "string", Option.AUTOMATIC, False,
           "Log file for debugging information."),
    Option("StatsLog", "${SpoolDir}/stats.log", "string", Option.AUTOMATIC, False,
           "Log file for statistics."),
    Option("DefaultStoreDir", "${SpoolDir}/stores", "string", Option.AUTOMATIC, False,
           "Default directory where Broker data stores will be written if user has not provided further customizations on a per-store basis."),

    Option("SitePolicyPath", "${PolicyDir}/site", "string", Option.USER, False,
           "Directories to search for local (i.e., site-specific) policy files, separated by colons. For each such directory, all files and subdirectories are copied to PolicyDirSiteInstall during zeekctl 'install' or 'deploy' (however, if the same file or subdirectory is found in more than one such directory, then only the first one encountered will be used)."),
    Option("SitePluginPath", "", "string", Option.USER, False,
           "Directories to search for custom plugins (i.e., plugins that are not included with zeekctl), separated by colons."),

    Option("PolicyDirSiteInstall", "${SpoolDir}/installed-scripts-do-not-touch/site", "string", Option.AUTOMATIC, False,
           "Directory where the shell copies local (i.e., site-specific) policy scripts when installing."),
    Option("PolicyDirSiteInstallAuto", "${SpoolDir}/installed-scripts-do-not-touch/auto", "string", Option.AUTOMATIC, False,
           "Directory where the shell copies auto-generated local policy scripts when installing."),

    # Internal, not documented.
    Option("ZeekCtlConfigDir", "${SpoolDir}", "string", Option.INTERNAL, False,
           """Directory where the shell copies the zeekctl-config.sh
           configuration file. If this is changed, the symlink created in
           CMakeLists.txt must be adapted as well.""", "BroCtlConfigDir"),
]

def print_options(category):
    out = ""
    err = ""

    for opt in sorted(options, key=lambda o: o.name):

        if opt.category != category:
            continue

        if not opt.type:
            err += "no type given for %s\n" % opt.name

        if opt.type == "string":
            if opt.default:
                opt.default = '"%s"' % opt.default
            else:
                opt.default = "_empty_"

        default = ", default %s" % opt.default

        default = default.replace("{", "\\{")
        description = opt.description.replace("{", "\\{")

        out += ".. _%s:\n\n*%s* (%s%s)\n    %s\n\n" % (opt.name, opt.name, opt.type, default, description)

    return (out, err)

