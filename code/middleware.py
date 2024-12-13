# to run: uvicorn middleware:app --reload

import logging
import subprocess
import time
import random
import string
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import json

app = FastAPI()
nodes = ["node0", "node1.harshproject.ufl-eel6871-fa24-pg0.utah.cloudlab.us", "node2.harshproject.ufl-eel6871-fa24-pg0.utah.cloudlab.us"]

try:
    # If running inside a cluster
    config.load_incluster_config()
except config.ConfigException:
    # If running outside the cluster
    config.load_kube_config()

logging.basicConfig(
    level=logging.DEBUG,  # Set the desired log level here (DEBUG, INFO, etc.)
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    filename='middleware_logfile.log'
)

def generate_random_string(length=4):
    characters = string.ascii_lowercase + string.digits
    random_string = ''.join(random.choice(characters) for _ in range(length))
    return random_string

def parse_args(job):
    elements = job.split()
    pairs = [(elements[i], elements[i + 1]) for i in range(1, len(elements), 2)]
    formatted_output = ', '.join(f'"{key}", "{value}"' for key, value in pairs)
    return formatted_output

def write_yaml(pod_name, args, node, out_file):
    pod_str = f'''
apiVersion: v1
kind: Pod
metadata:
  name: {pod_name}
spec:
  restartPolicy: Never
  containers:
  - image: docker.io/polinux/stress-ng:latest
    name: stress-container
    env:
    - name: DELAY_STARTUP
      value: "20"
    ports:
    - containerPort: 8080
    livenessProbe:
      httpGet:
        path: /actuator/health
        port: 8080
      initialDelaySeconds: 30
    args: [{args}]
  nodeSelector:
    kubernetes.io/hostname: {node}
    '''
    with open(out_file, 'w') as f:
        f.write(pod_str)

@app.get("/fetch_all_nodes")
def fetch_all_nodes():
    api_instance = client.CoreV1Api()
    try:
        node_list = api_instance.list_node()
        node_names = [node.metadata.name for node in node_list.items]
        return {"success": True, "nodes": node_names}
    except ApiException as e:
        return {"success": False, "node": None}

def get_node_cpu_capacity(node_name):
    try:
      command = ["kubectl", "get", "node", node_name, "-o", "json"]
      result = subprocess.run(command, capture_output=True, text=True)
      node_info = json.loads(result.stdout)
      cpu_capacity_cores = int(node_info["status"]["capacity"]["cpu"])
      logging.info(f"Node {node_name} CPU capacity in cores: {cpu_capacity_cores}")
      return cpu_capacity_cores * 1e9
    except Exception as e:
        return None

@app.get("/get_all_nodes_cpu")
async def get_all_nodes_cpu():
    try:
        print("line 1")
        usage = {}
        api = client.CustomObjectsApi()
        print("line 2")
        k8s_nodes = api.list_cluster_custom_object("metrics.k8s.io", "v1beta1", "nodes")
        print("line 3: ")
        print(k8s_nodes)
        for stats in k8s_nodes["items"]:
            node_name = stats["metadata"]["name"]
            cpu_usage_nanoseconds = int(stats["usage"]["cpu"].rstrip("n"))
            cpu_capacity_nanocores = get_node_cpu_capacity(node_name)
            if cpu_capacity_nanocores:
                usage[node_name] = (cpu_usage_nanoseconds / cpu_capacity_nanocores) * 100
    except Exception as e:
        print("Errrror")
        print(e)
    return usage

@app.post("/add_node")
async def add_node(request: Request):
    data = await request.json()
    node_name = data.get("node")
    api_instance = client.CoreV1Api()
    node_metadata = client.V1ObjectMeta(name=node_name)
    node_spec = client.V1NodeSpec()
    node = client.V1Node(metadata=node_metadata, spec=node_spec)

    try:
        api_response = api_instance.create_node(body=node)
        logging.info(f"Added new node: {node_name}")
        return {"success": True, "status": "Node created successfully", "node_name": node_name}
    except ApiException as e:
        if e.status == 409:
            # Node already exists
            return {"success": False, "status": "Node already exists"}
        else:
            # Other API exceptions
            raise {"success": False, "status": "unknown exception occured"}

@app.post("/add_pod")
async def add_pod(request: Request):
    try:
        data = await request.json()
        node_hostname = data.get("node_hostname")
        job = data.get("job")
        logging.info(f"Adding pod with job '{job}' to node {node_hostname[:5]}")
        pod_name = "stress-pod-"+generate_random_string()
        out_file = pod_name + ".yaml"
        job = parse_args(job=job)
        write_yaml(pod_name, job, node_hostname, out_file)
        command = f"kubectl apply -f {out_file}"
        time.sleep(2)
        result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        logging.info(f"Pod {pod_name} created on node {node_hostname[:5]}")
    except Exception as e:
        logging.critical(f"Error while creating pod {pod_name} in {node_hostname[:5]}")
        return {"success": False, "pod_name": None}
    return {"success": True, "pod_name": pod_name}

def delete_all_pods_in_node(node_name, api_instance):
    pod_list = api_instance.list_pod_for_all_namespaces(field_selector=f'spec.nodeName={node_name}')
    pods_deleted = []
    for pod in pod_list.items:
          namespace = pod.metadata.namespace
          pod_name = pod.metadata.name

          api_instance.delete_namespaced_pod(
              name=pod_name,
              namespace=namespace,
              body=client.V1DeleteOptions()
          )

          pods_deleted.append({"namespace": namespace, "pod_name": pod_name})

@app.post("/kill_node")
async def kill_node(request: Request):
    data = await request.json()
    node_name = str(data.get("node_name"))
    api_instance = client.CoreV1Api()

    print("hello inside kill node", node_name)
    delete_all_pods_in_node(node_name, api_instance)
    print("hello inside kill node after deleting all pods")
    try:
        api_instance.delete_node(node_name)
        print("hello inside kill node after deleting node")
    except Exception as e:
        print("hello inside kill node: exception in kill node", e)
        return {"success": False, "error": e}
    return {"sucess": True, "error": None}

@app.post("kill_pod")
async def kill_pod(request: Request):
    data = await request.json()
    pod_name = data.get("pod_name")

    api_instance = client.CoreV1Api()
    api_instance.delete_namespaced_pod(
        name=pod_name,
        namespace="default",
        body=client.V1DeleteOptions()
    )
    logging.info(f"Killed pod '{pod_name}'")
    return {"success": True, "error": None}

@app.post("/get_num_of_pods")
async def get_num_of_pods(request: Request):
    data = await request.json()
    node_name = data.get("node_name")
    api_instance = client.CoreV1Api()

    try:
        field_selector = f"spec.nodeName={node_name}"
        pod_list = api_instance.list_namespaced_pod(namespace="default", field_selector=field_selector)
        pod_count = 0
        for pod in pod_list.items:
            if pod.status.phase not in ["Succeeded", "Failed"]:
                pod_count += 1
        logging.info(f"Number of pods on node {node_name}: {pod_count}")
        return {"success": True, "pod_num": pod_count, "error": None}
    except Exception as e:
        logging.error(f"Error in get_pod_num: {e}")
        return {"success": False, "error": str(e), "pod_num": 0}
