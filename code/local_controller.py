import time
import threading
from fastapi import FastAPI, Request
from kubernetes import config
import logging
from datetime import datetime
import requests
import math
import sys

nodes = ["node0", "node1.harshproject.ufl-eel6871-fa24-pg0.utah.cloudlab.us", "node2.harshproject.ufl-eel6871-fa24-pg0.utah.cloudlab.us"]

app = FastAPI()

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    #filename='lc_logfile.log'
)

pi_kp = -3.127
pi_ki = 3.1406

sampling_rate = 5
reference_input = 0.8
job_list = []
node_name = "node0"
cur_pod_id = 0
max_max_pod = 12
job_delay = 15
read_jobs = False
last_pod_start_time = None
max_pod = (
    1
)
CPU_data = []
max_pod_data = []
controller_running = False

get_all_nodes_cpu_url = "http://128.110.217.116:6666/get_all_nodes_cpu"
get_num_of_pods_url = "http://128.110.217.116:6666/get_num_of_pods"
add_pod_url = "http://128.110.217.116:6666/add_pod"

def get_all_nodes_cpu(node_name):
    try:
        response = requests.get(get_all_nodes_cpu_url)
        if response.status_code == 200:
            cpu_data = response.json()
            return math.ceil(cpu_data[node_name] * 100) / 100 / 100, None
        else:
            return None, f"Error: {response.status_code}"
    except Exception as e:
        return None, e

def get_num_of_pods():
    try:
        payload = {"node_name": node_name}
        response = requests.post(get_num_of_pods_url, json=payload)
        if response.status_code == 200:
            res = response.json()
            return res["pod_num"], None
        else:
            return None, f"Error: {response.status_code}"
    except Exception as e:
        return None, e

def add_pod(job_des, node):
    try:
        global cur_pod_id
        payload = {"job": job_des, "node_hostname": node}
        cur_pod_id += 1
        response = requests.post(add_pod_url, json=payload)
        print("finddddddd 1", response, response.status_code)
        if response.status_code == 200:
            res = response.json()
            print("finddddddd 2", res, res.get("success"), res.get("msg"))
            return res.get("success"), res.get("msg")
        else:
            return False, f"Error: {response.status_code}"
    except Exception as e:
        return None, e

class PIController:
    def __init__(self, kp, ki, current_node):
        global node_name
        self.kp = kp
        self.ki = ki
        self.prev_e = 0
        self.integral = 0
        node_name = current_node
        self.node_name = current_node

    def compute(self, actual_value):
        err = reference_input - actual_value
        self.integral += sampling_rate * err
        u = self.kp * err + self.integral * self.ki
        self.prev_e = err

        u = max(1, round(u))
        return u

def closed_loop(controller):
    global max_pod, reference_input, CPU_data, max_pod_data, sampling_rate, last_pod_start_time, job_delay, controller_running
    logging.info("start close loop")
    pod_num = 0
    while True:
        if not controller_running:
            logging.info("controller stopped")
            time.sleep(sampling_rate)
            continue

        cur_cpu, msg = get_all_nodes_cpu(controller.node_name)
        if msg != None:
            # error getting the cpu
            logging.critical(f"error getting the CPU: {msg}")
            logging.critical(f"setting CPU to be 0")
            cur_cpu = 0

        logging.info(f"current CPU: {cur_cpu}")
        CPU_data.append(cur_cpu)

        pod_num, msg = get_num_of_pods()
        if msg is not None:
            logging.critical(f"error when getting pod number, {msg}")
            logging.critical(f"using previous pod number, {pod_num}")
        time_since_last_job_created = (
            (datetime.now() - last_pod_start_time).total_seconds()
            if last_pod_start_time is not None
            else float("inf")
        )
        if (pod_num > max_pod and cur_cpu > reference_input) or (
            pod_num < max_pod and cur_cpu < reference_input
        ):
            logging.info(
                f"max_pod {max_pod} != pod_num {pod_num}, skipping closed loop"
            )
        elif time_since_last_job_created < job_delay and cur_cpu < reference_input:
            logging.info(
                f"last job started {time_since_last_job_created}s ago, skipping closed loop, max_pod {max_pod}"
            )
        else:
            e = reference_input - cur_cpu
            u = controller.compute(e)
            logging.info(f"closed loop: e: {e}, u: {u}")
            new_max_pod = round(u)
            if new_max_pod >= max_max_pod:
                new_max_pod = max_max_pod
                logging.info(f"maxpod hitting upper bound {max_max_pod}")
            if new_max_pod > max_pod:
                logging.info(f"scaling up, max_pod {max_pod} -> {new_max_pod}")
            elif new_max_pod < max_pod:
                logging.info(f"scaling down, max_pod {max_pod} -> {new_max_pod}")
            else:
                logging.info(f"max_pod remains {max_pod}")
            max_pod = new_max_pod

        max_pod_data.append(max_pod)
        logging.info(f"AFTER ONE CONTROL DECISION: MAXPODS = {max_pod}, CPU = {cur_cpu}")
        time.sleep(sampling_rate)

@app.get("/start")
async def start_controller():
    """Start the controller"""
    global controller_running
    try:
        controller_running = True
        return {"success": True, "msg": ""}
    except Exception as e:
        logging.error(f"Error starting the local controller: {e}")
        return {"success": False, "msg": str(e)}

@app.get("/stop")
async def stop_controller():
    """Stop the controller."""
    global controller_running
    try:
        controller_running = False
        return {"success": True, "msg": ""}
    except Exception as e:
        logging.error(f"Error stopping the local controller: {e}")
        return {"success": False, "msg": str(e)}

@app.get("/pod-num")
async def get_nodes():
    """Return the current pod number."""
    try:
        res, msg = get_num_of_pods()
        if res is None:
            return {"success": False, "msg": msg, "pod-num": 0}
        else:
            return {"success": True, "msg": "", "pod-num": res}
    except Exception as e:
        logging.error(f"Error in get_nodes: {e}")
        return {"success": False, "msg": str(e), "pod-num": 0}

@app.get("/maxpod")
async def get_maxpod():
    """Return the current maxpod number."""
    try:
        return {"success": True, "msg": "", "maxpod": max_pod}
    except Exception as e:
        logging.error(f"Error in get_maxpod: {e}")
        return {"success": False, "msg": str(e), "maxpod": 0}

@app.post("/job")
async def handle_post(request: Request):
    """Add a new job."""
    global job_list, last_pod_start_time
    try:
        data = await request.json()
        job_description = data.get("job")
        node = data.get("node")

        logging.info(f"Getting new job from the endpoint: {job_description}")
        cur_pod_num, msg = get_num_of_pods()
        if cur_pod_num >= max_pod:
            logging.info("cur_pod_num >= max_pod, can't assign new job")
            return {
                "success": False,
                "msg": f"cur_pod_num {cur_pod_num} >= max_pod {max_pod}, can't assign new job",
            }

        logging.info(f"Current pod num: {cur_pod_num}, scheduling job {job_description}")
        print("finddddddd -1", job_description, node)
        ok, msg = add_pod(job_description, node)
        print("finddddddd 3", ok, msg)
        if not ok:
            logging.error(f"Error when trying to run job: {msg}")
            return {"success": False, "msg": f"Error trying to start new job, err: {msg}"}

        last_pod_start_time = datetime.now()
        logging.info(f"Job scheduled successfully")
        return {"success": True, "msg": ""}
    except Exception as e:
        logging.error(f"Error in handle_post: {e}")
        return {"success": False, "msg": str(e)}

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        #filename='lc_logfile.log'
    )
    args = sys.argv
    if len(args) < 2:
        print("Enter valid node index in the argument (0, 1 or 2)")
        exit(0)
    curr_node_index = int(args[1])
    if curr_node_index not in (0, 1, 2):
        print("Enter valid node index in the argument (0, 1 or 2)")
    
    current_node = nodes[curr_node_index]

    # to reduce log noise from requests APIs
    logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)

    # start a thread to read the CPU usage and update max_pod
    controller = PIController(pi_kp, pi_ki, current_node)
    closed_loop_thread = threading.Thread(target=closed_loop, args=(controller,))
    closed_loop_thread.daemon = True
    closed_loop_thread.start()

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=6667)
