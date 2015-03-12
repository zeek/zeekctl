import json

#TODO Graph class can replace whole nodestore in config.py
# and store all information on cluster nodes and peers in hierarchy
# to maintain compatibility with legacy code currently not implemented

class BGraph:

    def __init__(self):
        self.graph = {}
        self.edge_list = []
        self.root = ""
        self.node_attr = {}

    def addNode(self, node):
        if node in self.graph:
            raise RuntimeError("Node already exists")
        self.graph[node] = set()

    def addNodeAttr(self, node, attr, val):
        self.addNode(node)
        self.addAttr(node, attr, val)

    def addAttr(self, node, attr, val):
        if attr not in self.node_attr.keys():
            self.node_attr[attr] = {}
            attr_dict = {}
            attr_dict[node] = val
            self.node_attr[attr] = attr_dict
        elif node in self.node_attr[attr].keys():
            raise RuntimeError("Node already exists")
        else:
            self.node_attr[attr][node] = val

    def addEdge(self, u, v):
        if u in self.graph and v in self.graph[u]:
            raise RuntimeError("Edge already exists")
        self.graph[u].add(v)
        self.edge_list.append((u, v))

    def setRoot(self, root):
        self.root = root

    def finalize(self):
        if not self.graph:
            raise RuntimeError("Graph is empty")
        node = self.graph.keys()[0]
        next = node
        while next:
            node = next
            next = self.getPredecessor(node)
        self.setRoot(node)

    def getRoot(self):
        if not self.root:
            self.finalize()
        return self.root

    def size(self):
        return len(self.graph)

    def empty(self):
        return self.size() == 0

    def getGraph(self):
        return self.graph

    def nodes(self):
        return self.graph.keys()

    def edges(self):
        return self.edge_list

    def getSubgraph(self, sroot):
        if sroot not in self.graph:
            print "sroot " + str(sroot) + " not found among"
            for n in self.nodes():
                print " - " + str(n)
            raise RuntimeError("Node not found")

        sg = BGraph()
        sg.addNode(sroot)
        self.copyNodeAttr(sg, sroot)
        sg.setRoot(sroot)

        visit = [sroot]
        while len(visit) != 0:
            node = visit.pop()
            # print("node chosen " + node)
            for succ in self.getSuccessors(node):
                sg.addNode(succ)
                self.copyNodeAttr(sg, succ)
                sg.addEdge(node, succ)
                visit.append(succ)

        return sg

    def getNeighbors(self, node):
        neighbors = set()
        for (u, v) in self.edge_list:
            if u == node:
                neighbors.add(v)
            elif v == node:
                neighbors.add(u)
        return neighbors

    def getSuccessors(self, node):
        if node not in self.graph:
            raise RuntimeError("Node " + str(node) + " does not exist")
        return self.graph[node]

    def getRootSuccessors(self):
        return self.getSuccessors(self.getRoot())

    def getPredecessor(self, node):
        predList = []
        pred = ""
        for (u, v) in self.edge_list:
            if v == node:
                pred.append(u)
                pred = u

        if (len(predList) > 1):
            raise RuntimeError("More than one predecessor in hierarchy")

        return pred

    def getNodeAttr(self, node):
        attr_list = []
        for attr in self.node_attr.keys():
            if node in self.node_attr[attr]:
                attr_list.append(attr)

        return attr_list

    def getAttrNodes(self, attr):
        attr_list = []
        if attr not in self.node_attr:
            return attr_list
        else:
            return self.node_attr[attr].keys()

    def getAttrNodeVal(self, attr, node):
        if attr not in self.node_attr:
            return None
        elif node not in self.node_attr[attr]:
            return None
        else:
            return self.node_attr[attr][node]

    def copyNodeAttr(self, sgraph, node):
        attributes = self.getNodeAttr(node)
        for a in attributes:
            sgraph.addAttr(node, a, self.getAttrNodeVal(a, node))

        return sgraph

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
        if not self.root:
            self.finalize()
        visited = set()
        known = set()
        known.add(self.root)

        while known:
            node = known.pop()
            if node not in visited:
                visited.add(node)
                known = known | self.graph[node]

        return len(visited) == self.size()
