import json
import os.path
import subprocess
from pathlib import Path

import ZeekControl.config
import ZeekControl.plugin
from ZeekControl.exceptions import ConfigurationError


class ClusterBackendZeroMQ(ZeekControl.plugin.Plugin):
    def __init__(self):
        super().__init__(apiversion=1)

    def name(self):
        return "cluster_backend_zeromq"

    def pluginVersion(self):
        return 1

    def options(self):
        return [
            (
                "disable_unencrypted_warning",
                "bool",
                False,
                "Disable the multi-node unencrypted warning.",
            ),
            (
                "use_curve_encryption",
                "string",
                "auto",
                "Whether to enable ZeroMQ CURVE-based encryption for cluster communication (auto, 0 or 1)",
            ),
            (
                "curve_dir",
                "string",
                "${SpoolDir}/zeromq/curve",
                "Directory to persistently store client and server curve keys on the manager",
            ),
        ]

    def generate_keypair(self, publickey: Path, secretkey: Path):
        """
        Generate the ZeroMQ CURVE keypair in Z85 encoded format and write
        them to the files pointed at by publickey and secretkey. The keys
        themselves are generated using zeek and calling the appropriate BiF.
        """
        zeek = self.getGlobalOption("zeek")
        if not os.path.lexists(zeek):
            raise ConfigurationError(f"cannot find Zeek binary: {zeek}")

        args = [
            zeek,
            "-b",
            "-e",
            "print to_json(Cluster::Backend::ZeroMQ::generate_keypair())",
        ]
        output = subprocess.check_output(args)
        loaded = json.loads(output)
        public, secret = loaded["public"], loaded["secret"]
        if len(public) != 40 or len(secret) != 40:
            raise ConfigurationError(
                f"failed to create ZeroMQ CURVE keypair {loaded!r}"
            )

        publickey.touch(exist_ok=True)
        publickey.chmod(0o600)
        publickey.write_text(public + "\n")

        secretkey.touch(exist_ok=True)
        secretkey.chmod(0o600)
        secretkey.write_text(secret + "\n")

    def init(self):
        """
        Enable the plugin if ClusterBackend setting is ZeroMQ.
        """
        backend = self.getGlobalOption("ClusterBackend")
        if backend.lower() != "zeromq":
            return False

        # Switch topic separator for node topics to "." as that's what
        # the ZeroMQ cluster backend uses.
        if not self.getGlobalOption("ClusterTopicSeparator"):
            ZeekControl.config.Config.set_option("ClusterTopicSeparator", ".")

        # Lookup ZeekPort from the config and increment it by two. Use these two
        # ports to configure the XPUB/XSUB proxy component. The magic Port class
        # is located over in install.py
        base_port = ZeekControl.config.Config.get_option("ZeekPort")
        self.xpub_port = base_port
        self.xsub_port = base_port + 1
        ZeekControl.config.Config.set_option("ZeekPort", base_port + 2)

        # The manager address is used for listening of the XPUB/XSUB proxy.
        self.xpub_xsub_addr = ZeekControl.config.Config.manager().addr

        # If the address looks like an IPv6 address, put brackets around it
        # so that libzmq does not interpret it as a device and instead as
        # an IPv6 address.
        if ":" in self.xpub_xsub_addr:
            self.xpub_xsub_addr = "[" + self.xpub_xsub_addr + "]"

        # Check if this is a multi-node cluster (multiple IP addresses) and
        # tell the user about it.
        addrs = {n.addr for n in self.nodes()}

        # If use_curve_encryption is "auto", determine 0 or 1 based on
        # the number of different node addresses available. If it is
        # already "0" or "1", just make it the integer value.
        self.use_curve_encryption = (
            self.getOption("use_curve_encryption").lower().strip()
        )
        if len(addrs) > 1 and self.use_curve_encryption == "auto":
            self.use_curve_encryption = 1
        elif len(addrs) == 1 and self.use_curve_encryption == "auto":
            self.use_curve_encryption = 0
        elif self.use_curve_encryption in ["0", "1"]:
            self.use_curve_encryption = int(self.use_curve_encryption)
        elif self.use_curve_encryption in ["true", "false"]:
            self.use_curve_encryption = 1 if self.use_curve_encryption == "true" else 0
        else:
            raise ConfigurationError(
                f"invalid UseCurveEncryption value: {self.use_curve_encryption}"
            )

        # Store public and secret keys in in spool/zeromq/curve by default.
        curve_dir = self.getOption("curve_dir")
        self.server_publickey = Path(curve_dir) / "server_publickey"
        self.server_secretkey = Path(curve_dir) / "server_secretkey"
        self.client_publickey = Path(curve_dir) / "client_publickey"
        self.client_secretkey = Path(curve_dir) / "client_secretkey"

        # If encryption is enabled, create the spool directory for
        # the server and client keypairs and generate them if needed.
        if self.use_curve_encryption:
            os.makedirs(curve_dir, exist_ok=True)
            os.chmod(curve_dir, 0o700)

            if not self.server_publickey.exists() or not self.server_secretkey.exists():
                self.message("Generating ZeroMQ CURVE server keypair...")
                self.generate_keypair(self.server_publickey, self.server_secretkey)

            if not self.client_publickey.exists() or not self.client_secretkey.exists():
                self.message("Generating ZeroMQ CURVE client keypair...")
                self.generate_keypair(self.client_publickey, self.client_secretkey)

        if (
            not self.use_curve_encryption
            and len(addrs) > 1
            and not self.getOption("disable_unencrypted_warning")
        ):
            self.message(
                f'Warning: ZeroMQ encryption disabled, but multi-node cluster detected (IPs {", ".join(addrs)}).'
            )
            self.message(
                "\nYou may disable this warning by setting the following option in zeekctl.cfg:"
            )
            self.message(
                "\n    cluster_backend_zeromq.disable_unencrypted_warning = 1\n"
            )
            self.message(
                "\nYou may enable encryption by setting the following option.cfg:"
            )
            self.message(
                "\n    cluster_backend_zeromq.use_curve_encryption = 1 (or auto)\n"
            )

        # If any of the addresses used by nodes looks like an IPv6 address,
        # enable ZeroMQ IPv6 support via the configuration knob.
        self.ipv6 = False
        if any(":" in a for a in addrs):
            self.ipv6 = True

        return True

    def zeekctl_config(self):
        """
        Zeek 7.1 and later ship the following policy script to enable ZeroMQ.
        """
        script = "\n".join(
            [
                "# Enable ZeroMQ - the zeromq/connect script was deprecated with 8.1",
                '@if ( Version::at_least("8.1.0") )',
                "@load policy/frameworks/cluster/backend/zeromq",
                "@else",
                "@load policy/frameworks/cluster/backend/zeromq/connect",
                "@endif",
                "",
                f'redef Cluster::Backend::ZeroMQ::listen_xpub_endpoint = "tcp://{self.xpub_xsub_addr}:{self.xpub_port}";',
                f'redef Cluster::Backend::ZeroMQ::listen_xsub_endpoint = "tcp://{self.xpub_xsub_addr}:{self.xsub_port}";',
                f'redef Cluster::Backend::ZeroMQ::connect_xpub_endpoint = "tcp://{self.xpub_xsub_addr}:{self.xsub_port}";',
                f'redef Cluster::Backend::ZeroMQ::connect_xsub_endpoint = "tcp://{self.xpub_xsub_addr}:{self.xpub_port}";',
                "",
                f'redef Cluster::Backend::ZeroMQ::ipv6 = {"T" if self.ipv6 else "F"};',
                "",
            ]
        )

        # If CURVE encryption is enabled, redef the server and client
        # keys into the zeekctl-config file.
        if self.use_curve_encryption:

            def render_redef(path: Path) -> str:
                """
                Small helper to render a redef line given the path to
                the keypair files stored in curve_dir.
                """
                what = path.parts[-1]
                value = path.read_text().strip()
                if len(value) != 40:
                    raise ConfigurationError(f"CURVE key {what} not 40 bytes long")

                return "\n".join(
                    [
                        f"@if ( |Cluster::Backend::ZeroMQ::curve_{what}| == 0 )",
                        f'redef Cluster::Backend::ZeroMQ::curve_{what} = "{value}";',
                        "@endif",
                    ]
                )

            script += "\n".join(
                [
                    "",
                    "# Public and secret server keys for ZeroMQ CURVE encryption.",
                    render_redef(self.server_publickey),
                    render_redef(self.server_secretkey),
                    "",
                    "# Public and secret client keys for ZeroMQ CURVE encryption.",
                    render_redef(self.client_publickey),
                    render_redef(self.client_secretkey),
                    "",
                ]
            )

        # Usually this runs automatically on the manager, but Zeectl supports
        # standalone mode and the node doesn't know it should run the proxy
        # thread for WebSocket functionality.
        if ZeekControl.config.Config.standalone:
            script += "\n".join(
                [
                    "",
                    "# Standalone: Run the XPUB/XSUB thread in standalone mode",
                    "redef Cluster::Backend::ZeroMQ::run_proxy_thread = T;",
                    "",
                    "# Standalone: Subscribe to zeek.cluster.node.zeek.",
                    "#             for controllee WebSocket interactions.",
                    "event zeek_init()",
                    "	{",
                    '	Cluster::subscribe("zeek.cluster.node.zeek.");',
                    "	}",
                ]
            )

        return script
