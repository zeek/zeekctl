
class BGraph:

    def __init__(self):
        self.graph = {}
        self.edges = []
        self.root = ""

    def addNode(self, node):
        if node in self.graph:
            raise RuntimeError("Node already exists")
        self.graph[node] = set()
        #FIXME This is a hack, first node becomes root
        if not self.root:
            self.root = node

    def addEdge(self, u, v):
        if u in self.graph and v in self.graph[u]:
            raise RuntimeError("Edge already exists")
        self.graph[u].add(v)
        self.edges.append((u, v))

    def set_root(self, root):
        print "root is " + str(root)
        self.root = root

    def size(self):
        return len(self.graph)

    def get_graph(self):
        return self.graph

    def nodes(self):
        return self.graph.keys()

    def getSubgraph(self, sroot):
        if sroot not in self.graph:
            raise RuntimeError("Node not found")

        sg = BGraph()
        sg.addNode(sroot)

        visit = [sroot]
        while len(visit) != 0:
            node = visit.pop()
            # print("node chosen " + node)
            for succ in self.getSuccessors(node):
                sg.addNode(succ)
                sg.addEdge(node, succ)
                visit.append(succ)
        return sg

    def getNeighbors(self, node):
        neighbors = set()
        for (u, v) in self.edges:
            if u == node:
                neighbors.add(v)
            elif v == node:
                neighbors.add(u)
        return neighbors

    def getSuccessors(self, node):
        return self.graph[node]

    def getPredecessor(self, node):
        pred = []
        for (u, v) in self.edges:
            if v == node:
                pred.append(u)
        if not pred or (len(pred) > 1):
            raise RuntimeError("No or more than one predecessor")
        else:
            return pred.pop()

    def isConnected(self):
        visited = set()
        known = set()
        node = self.nodes()[0]
        known.add(node)

        while known:
            vis = known.pop()
            if vis not in visited:
                visited.add(vis)
                known = known | self.getNeighbors(vis)

        return len(visited) == self.size()

    def isTree(self):
        visited = set()
        known = set()
        known.add(self.root)

        while known:
            node = known.pop()
            if node not in visited:
                visited.add(node)
                known = known | self.graph[node]

        return len(visited) == self.size()
# End BGraph
