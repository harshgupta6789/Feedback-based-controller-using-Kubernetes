import time
import threading
import requests
import logging
from datetime import datetime
from fastapi import FastAPI, Request

nodes = ["node0", "node1.harshproject.ufl-eel6871-fa24-pg0.utah.cloudlab.us", "node2.harshproject.ufl-eel6871-fa24-pg0.utah.cloudlab.us"]

fetch_all_nodes_url = "http://127.0.0.1:6666/fetch_all_nodes"
add_node_url = "http://127.0.0.1:6666/add_node"
kill_node_url = "http://127.0.0.1:6666/kill_node"
get_all_nodes_cpu_url = "http://127.0.0.1:6666/get_all_nodes_cpu"
get_num_of_pods_url = "http://127.0.0.1:6666/get_num_of_pods"

# settings
sampling_time = 1
scaling_sleep_time = 2
master_index = 0
worker_indices = [1, 2]

node_url = {
    nodes[0]: "http://127.0.0.1:6667/",
    nodes[1]: "http://128.110.217.125:6667/",
    nodes[2]: "http://128.110.217.128:6667/",
}

node_job_api = {
    nodes[0]: node_url[nodes[0]] + "job",
    nodes[1]: node_url[nodes[1]] + "job",
    nodes[2]: node_url[nodes[2]] + "job",
}

node_pod_api = {
    nodes[0]: node_url[nodes[0]] + "pod-num",
    nodes[1]: node_url[nodes[1]] + "pod-num",
    nodes[2]: node_url[nodes[2]] + "pod-num",
}

reference_input = 0.8
prev_cpu_to_consider = 2
node_start_delay = (30)

job_assign_interval = 15
jobs_file_name = "jobs.txt"

clusterwide_cpu = []  # recent cluster CPU usage
started_nodes = ["node0"]
worker_nodes = ["node1.harshproject.ufl-eel6871-fa24-pg0.utah.cloudlab.us", "node2.harshproject.ufl-eel6871-fa24-pg0.utah.cloudlab.us"]
last_started_time = datetime.now()
job_list = []

# @app.get("/assign_jobs_api")
# async def assign_jobs_api(request: Request):
#     global started_nodes
#     try:
#         data = await request.json()
#         job_description = data.get("job")
#         for node in started_nodes:
#             ok, err = assign_job(job_description, node)
#             if ok:
#                 logging.info(f" Assigned job {job} to node {node}")
#                 break
#             else:
#                 logging.info(f"can't assign job {job} to node {node} because {err}")
#                 return {"success": False, "msg": "unknown"}
#         return {"success": True, "msg": ""}
#     except Exception as e:
#         logging.error(f"Error getting the new job: {e}")
#         return {"success": False, "msg": str(e)}

def get_num_of_pods(node_name):
    try:
        payload = {"node_name": node_name}
        response = requests.post(get_num_of_pods_url, json=payload)
        if response.status_code == 200:
            res = response.json()
            if res["success"]:
                return res["pod_num"], None
            else:
                return None, f"Error: {res['error']}"
        else:
            return f"Error: {response.status_code}"
    except Exception as e:
        return None, e

def get_max_pod(node):
    try:
        response = requests.get(node_url[node] + "maxpod")
        if response.status_code == 200:
            res = response.json()
            if res["success"]:
                return res["maxpod"], None
            else:
                return None, f"Error: {res['msg']}"
        else:
            return None, f"Error: {response.status_code}"
    except Exception as e:
        return None, e

def read_jobs(file_path):
    jobs = []
    try:
        with open(file_path, 'r') as f:
            for line in f:
                job = line.strip()
                if job and not job.startswith('#'):
                    jobs.append(job)
        logging.info(f"Loaded {len(jobs)} jobs from {file_path}.")
    except FileNotFoundError:
        logging.critical(f"Jobs file '{file_path}' not found.")
    return jobs

def fetch_all_nodes():
    try:
        response = requests.get(fetch_all_nodes_url)
        if response.status_code == 200:
            res = response.json()
            if res["success"]:
                return res["nodes"], None
            else:
                return None, f"Error: unknown"
        else:
            return None, f"Error: {response.status_code}"
    except Exception as e:
        return None, e

def get_cpu():
    try:
        response = requests.get(get_all_nodes_cpu_url)
        if response.status_code == 200:
            cpu_data = response.json()
            return cpu_data, None
        else:
            return None, f"Error: {response.status_code}"
    except Exception as e:
        return None, e

def kill_node(node_name):
    try:
        payload = {"node_name": node_name}
        response = requests.post(kill_node_url, json=payload)
        if response.status_code == 200:
            res = response.json()
            return res["success"], res["error"]
        else:
            return False, f"Error: {response.status_code} , payload: {str(payload)}"
    except Exception as e:
        return False, e

def start_controller(node_name):
    try:
        response = requests.get(node_url[node_name] + "start")
        if response.status_code == 200:
            res = response.json()
            return res["success"], res["msg"]
        else:
            return False, f"Error: {response.status_code}"
    except Exception as e:
        return False, e

def stop_controller(node_name):
    try:
        response = requests.get(node_url[node_name] + "stop")
        if response.status_code == 200:
            res = response.json()
            return res["success"], res["msg"]
        else:
            return False, f"Error: {response.status_code}"
    except Exception as e:
        return False, e

def add_node(node):
    try:
        payload = {"node": node}
        response = requests.post(add_node_url, json=payload)
        if response.status_code == 200:
            res = response.json()
            return res["success"], res["status"]
        else:
            return False, f"Error: {response.status_code}"
    except Exception as e:
        return False, e

def remove_worker(node_identifier):
    global worker_nodes, started_nodes
    
    # Remove from worker_nodes
    for idx, node in enumerate(worker_nodes):
        if node == node_identifier:
            worker_nodes.pop(idx)
            break
    
    # Remove from started_nodes
    for idx, node in enumerate(started_nodes):
        if node == node_identifier:
            started_nodes.pop(idx)
            break

def sample_cpu():
    """Sample the cluster CPU utilization."""
    global sampling_time, started_nodes, clusterwide_cpu
    current_time = 0
    
    while True:
        active_nodes, error_message = fetch_all_nodes()
        logging.debug(f"Active nodes: {active_nodes}")
        if error_message is not None:
            logging.critical(f"Error retrieving nodes, message: {error_message}")
            time.sleep(sampling_time)
            continue

        nodes_cpu_data, error_message = get_cpu()
        logging.debug(f"Nodes CPU data: {nodes_cpu_data}")
        if error_message is not None:
            logging.critical(f"Error retrieving node CPU data, message: {error_message}")
            time.sleep(sampling_time)
            continue

        total_cpu_utilization = 0
        node_count = 0
        total_pods_count = 0
        
        for node in started_nodes:
            # Handle missing or stopped nodes
            if node not in active_nodes:
                logging.error(f"Node {node} was started but is no longer active.")
                logging.info(
                    f"Removing node {node} from the worker nodes list as it stopped unexpectedly."
                )
                remove_worker(node)
                continue

            if node not in nodes_cpu_data:
                logging.error(f"Unable to retrieve CPU data for node {node}, assuming CPU usage is 0.")
                nodes_cpu_data[node] = 0

            # Retrieve pod count for the node
            pod_count, _ = get_num_of_pods(node)
            total_pods_count += pod_count

            logging.info(f"Node {node} CPU usage: {nodes_cpu_data[node]}")
            total_cpu_utilization += nodes_cpu_data[node] / 100
            node_count += 1

        if node_count != 0:
            current_cluster_cpu = total_cpu_utilization / node_count
            clusterwide_cpu.append(current_cluster_cpu)
            logging.info(f"Current cluster-wide CPU utilization: {current_cluster_cpu}")

        time.sleep(sampling_time)
        current_time += sampling_time

def controller():
    """Determine whether to scale up or scale down the cluster."""
    global started_nodes, clusterwide_cpu, prev_cpu_to_consider, reference_input, last_started_time
    while True:
        average_cluster_cpu = None
        
        # Ensure sufficient CPU data is available for decision-making
        if len(clusterwide_cpu) < prev_cpu_to_consider:
            logging.info("Insufficient CPU data. Skipping scaling decision.")
            time.sleep(scaling_sleep_time)
            continue
        else:
            # Calculate the average CPU usage based on recent data
            recent_cpu_data = clusterwide_cpu[-prev_cpu_to_consider:]
            average_cluster_cpu = sum(recent_cpu_data) / prev_cpu_to_consider
        
        if average_cluster_cpu > reference_input:
            # Scale-up decision: Check if more nodes can be started
            if len(started_nodes) == len(worker_nodes) + 1:
                logging.info("All nodes are active. No scaling up possible.")
            else:
                logging.info(
                    f"Cluster CPU average {average_cluster_cpu} exceeds threshold {reference_input}. Initiating scale-up."
                )
                new_node_to_add = worker_nodes[len(started_nodes) - 1]  # Skip master node
                success, error_message = add_node(new_node_to_add)
                if success:
                    success, controller_message = start_controller(new_node_to_add)
                    if success:
                        started_nodes.append(new_node_to_add)
                        logging.info(f"Successfully added node {new_node_to_add}. Resetting CPU data.")
                        clusterwide_cpu = []  # Clear CPU data for new monitoring cycle
                        last_started_time = datetime.now()
                    else:
                        logging.error(
                            f"Failed to start the controller for node {new_node_to_add}. Error: {controller_message}"
                        )
                else:
                    logging.error(
                        f"Failed to start node {new_node_to_add}. Error: {error_message}"
                    )
        else:
            logging.info(
                f"Cluster CPU average {average_cluster_cpu} is within acceptable range ({reference_input}). No scaling needed."
            )
        
        # Scale-down decision: Evaluate the possibility of reducing active nodes
        if (datetime.now() - last_started_time).total_seconds() > node_start_delay and len(started_nodes) > 1:
            # Consider the most recently added node for removal
            last_node = started_nodes[-1]

            # Check the pod count on the selected node
            pod_count, error_message = get_num_of_pods(last_node)
            if pod_count is None:
                logging.error(f"Unable to retrieve pod count for node {last_node}.")
            else:
                if pod_count == 0:
                    success, error_message = kill_node(last_node)
                    if not success:
                        logging.error(
                            f"Error encountered while removing node {last_node}. Details: {error_message}"
                        )
                    else:
                        success, controller_message = stop_controller(last_node)
                        started_nodes.pop()
                        logging.info(f"Node {last_node} removed successfully during scale-down.")
                        if not success:
                            logging.error(
                                f"Error while stopping controller for node {last_node}. Details: {controller_message}"
                            )
                else:
                    logging.info(
                        f"Node {last_node} has active pods ({pod_count}). Scale-down skipped."
                    )
        time.sleep(scaling_sleep_time)

def assign_job(job, node_name):
    """
    try to assign a job to a node
    """
    try:
        payload = {"node": node_name, "job": job}
        response = requests.post(node_job_api[node_name], json=payload)
        if response.status_code == 200:
            res = response.json()
            return res.get("success"), res.get("msg")
        else:
            return False, f"Error: {response.status_code}"
    except Exception as e:
        return False, e

def job_scheduling():
    global job_list
    current_job = 0
    while True:
        job = job_list[current_job]
        assigned = False
        for node in started_nodes:
            ok, err = assign_job(job, node)
            if ok:
                assigned = True
                logging.info(f" Assigned job {current_job+1}: {job} to node {node}")
                break
            else:
                logging.info(f"can't assign job {job} to node {node}, because {err}")
        if not assigned:
            logging.info(f"can't assign job {job} in this iteration.")
        else:
            current_job += 1
        if(current_job >= len(job_list)):
            break
        time.sleep(job_assign_interval)

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,  # Set the desired log level here (DEBUG, INFO, etc.)
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # to reduce log noise from requests APIs
    logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)

    ok, msg = start_controller("node0")
    if not ok:
        logging.error(f"error when starting the master node controller, error: {msg}")
    else:
        logging.info("master node local controller started")

    # read job list
    job_list = read_jobs(jobs_file_name)
    if job_list is None:
        logging.warning("Jobs list is empty or corrupted")
        exit(0)

    # start CPU sampling to update max pods
    logging.info("starting sampling")
    sample_cpu_thread = threading.Thread(target=sample_cpu)
    sample_cpu_thread.daemon = True
    sample_cpu_thread.start()

    # start controller to accept jobs
    logging.info("starting controller")
    controller_thread = threading.Thread(target=controller)
    controller_thread.daemon = True
    controller_thread.start()

    # starting job scheduling
    logging.info("starting job")
    job_thread = threading.Thread(target=job_scheduling)
    job_thread.daemon = True
    job_thread.start()

    while True:
        time.sleep(5)
