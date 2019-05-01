# Store results of a zeekctl command.

from ZeekControl import node as node_mod

class CmdResult:
    """Class representing the result of a zeekctl command."""

    def __init__(self, ok=True, unknowncmd=False):
        # Command succeeded (True), or error occurred (False)
        self.ok = ok

        # If True, then the requested command does not exist.
        self.unknowncmd = unknowncmd

        # Number of Zeek nodes that command succeeded, and number that failed
        self.success_count = 0
        self.fail_count = 0

        # List of results for each node
        self.nodes = []

        # Results in the "nodes" list have been sorted (True), or not (False)
        self._sorted = False

        # List of arbitrary (key, value) pairs.
        self.keyval = []

    def to_dict(self):
        return {
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "nodes": self.get_node_data(),
        }

    def get_node_counts(self):
        """Return tuple (success, fail) of success and fail node counts."""

        return self.success_count, self.fail_count

    def get_node_data(self):
        """Return a list of tuples (node, success, data), where node is a
        Zeek node, success is a boolean, and data is a dictionary.
        """

        results = self.nodes

        if not self._sorted:
            results.sort(key=node_mod.sorttuple)
            self._sorted = True

        return results

    def get_node_output(self):
        """Return a list of tuples (node, success, output), where node is a
        Zeek node, success is a boolean, and output is a string.
        """

        results = []
        for node, success, out in self.nodes:
            output = out.get("_output", "")
            results.append((node, success, output))

        if not self._sorted:
            results.sort(key=node_mod.sorttuple)
            self._sorted = True

        return results

    def set_node_fail(self, node):
        """Records the fact that the given node failed."""

        self.nodes.append((node, False, {}))
        self.fail_count += 1
        self.ok = False

    def set_node_success(self, node):
        """Records the fact that the given node succeeded."""

        self.nodes.append((node, True, {}))
        self.success_count += 1

    def set_node_output(self, node, success, output):
        """Records the success status of the given node, and stores some
        output messages.  The node parameter is a Zeek node, success is a
        boolean, and output is a string.
        """

        self.nodes.append((node, success, {"_output": output}))
        if success:
            self.success_count += 1
        else:
            self.fail_count += 1
            self.ok = False

    def set_node_data(self, node, success, data):
        """Records the success status of the given node, and stores some data.
        The node parameter is a Zeek node, success is a boolean, and data is a
        dictionary.
        """

        self.nodes.append((node, success, data))
        if success:
            self.success_count += 1
        else:
            self.fail_count += 1
            self.ok = False

