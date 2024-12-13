import subprocess
import time
import json

sampling_rate = 5
nodes = ["node0", "node1.harshproject.ufl-eel6871-fa24-pg0.utah.cloudlab.us", "node2.harshproject.ufl-eel6871-fa24-pg0.utah.cloudlab.us"]
node = -1

def get_node_capacity(node_name):
    command = ['kubectl', 'get', 'node', node_name, '-o', 'json']
    result = subprocess.run(command, capture_output=True, text=True)

    if result.returncode == 0:
        node_info = json.loads(result.stdout)
        cpu_capacity_str = node_info['status']['capacity']['cpu']
        if cpu_capacity_str.endswith("m"):
            cpu_capacity_nanocores = int(cpu_capacity_str[:-1]) * 1e6
        else:
            cpu_capacity_nanocores = int(cpu_capacity_str) * 1e9
        return cpu_capacity_nanocores
    else:
        print(f"Error getting node capacity: {result.stderr}")
        return None

def get_metrics(node_number):
    command = ['kubectl', 'get', '--raw', '/apis/metrics.k8s.io/v1beta1/nodes']
    
    result = subprocess.run(command, capture_output=True, text=True)
    
    if result.returncode == 0:
        metrics = json.loads(result.stdout)
        for node in metrics.get('items', []):
            node_name = node['metadata']['name']
            cpu_usage_str = node['usage']['cpu']
            if cpu_usage_str.endswith("n"):
                cpu_usage_nanocores = int(cpu_usage_str.rstrip('n'))
            else:
                cpu_usage_nanocores = int(cpu_usage_str.rstrip('m')) * 1e6

            cpu_capacity_nanocores = get_node_capacity(node_name)

            if cpu_capacity_nanocores:
                cpu_usage_percentage = (cpu_usage_nanocores / cpu_capacity_nanocores) * 100
                if node_number == 3:
                    print(f"Node: {node_name[:5]}, CPU Usage: {cpu_usage_percentage:.2f}%")
                elif node_name == nodes[node_number]:
                    print(f"Node: {node_name[:5]}, CPU Usage: {cpu_usage_percentage:.2f}%")
            else:
                print(f"Could not calculate CPU usage for node: {node_name}")
    else:
        print(f"Error getting metrics: {result.stderr}")
    if node_number == 3:
        print()

if __name__ == "__main__":
    while True:
        if node == -1:
            node = int(input("Enter 0 for node 0, 1 for node 1, 2 for node 2, 3 for all nodes: "))
        if node not in (0, 1, 2, 3):
            print("Enter valid input")
            break
        get_metrics(node)
        time.sleep(sampling_rate)
