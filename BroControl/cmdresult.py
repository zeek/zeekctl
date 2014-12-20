# Store results of a broctl command.

class CmdResult:
    """Class representing the result of a broctl command."""

    def __init__(self):
        self.ok = True
        self.success_count = 0
        self.fail_count = 0
        self.nodes = []

    def succeeded(self):
        """Return True if command succeeded, or False if an error occurred."""
        return self.ok

    def failed(self):
        """Return True if command failed, or False if no error occurred."""
        return not self.ok

    def get_node_counts(self):
        """Return tuple (success, fail) of success and fail node counts."""
        return self.success_count, self.fail_count

    def get_node_results(self):
        """Return a list of tuples (node, status, data)."""
        return self.nodes

    def set_cmd_fail(self):
        """Records the fact that the command failed."""
        self.ok = False

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
        """Records the success status of the given node and output message."""
        self.nodes.append((node, success, output))
        if success:
            self.success_count += 1
        else:
            self.fail_count += 1
            self.ok = False     

    def set_node_data(self, node, success, data):
        """Records the success status of the given node and some data."""
        self.nodes.append((node, success, data))
        if success:
            self.success_count += 1
        else:
            self.fail_count += 1
            self.ok = False

