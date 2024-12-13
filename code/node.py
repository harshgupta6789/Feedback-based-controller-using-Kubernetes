class Node:
    def __init__(self, name, address):
        self.name = name
        self.address = address
        self.currPods = 0
        self.maxPods = 0
        self.node_cpu_utilisation = 0.0
        self.is_active = True
