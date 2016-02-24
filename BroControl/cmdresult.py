# Store results of a broctl command.

class CmdResult:
    """Class representing the result of a broctl command."""

    def __init__(self):
        # Command succeeded (True), or error occurred (False)
        self.ok = True

        # Number of Bro nodes that command succeeded, and number that failed
        self.success_count = 0
        self.fail_count = 0

        # List of results for each node
        self.nodes = []

        # Results in the "nodes" list have been sorted (True), or not (False)
        self._sorted = False

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
        Bro node, success is a boolean, and data is a dictionary.
        """

        results = self.nodes

        if not self._sorted:
            results.sort(key=lambda n: (n[0].type, n[0].name))
            self._sorted = True

        return results

    def get_node_output(self):
        """Return a list of tuples (node, success, output), where node is a
        Bro node, success is a boolean, and output is a list.
        """

        results = []
        for node, success, out in self.nodes:
            output = out.get("_output", [])
            results.append((node, success, output))

        if not self._sorted:
            results.sort(key=lambda n: (n[0].type, n[0].name))
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
        output messages.  The node parameter is a Bro node, success is a
        boolean, and output is a list.
        """

        if output is None:
            # this is needed because runCmdsParallel can return None
            outlines = []
        else:
            outlines = output
        self.nodes.append((node, success, {"_output": outlines}))
        if success:
            self.success_count += 1
        else:
            self.fail_count += 1
            self.ok = False

    def set_node_data(self, node, success, data):
        """Records the success status of the given node, and stores some data.
        The node parameter is a Bro node, success is a boolean, and data is a
        dictionary.
        """

        self.nodes.append((node, success, data))
        if success:
            self.success_count += 1
        else:
            self.fail_count += 1
            self.ok = False

