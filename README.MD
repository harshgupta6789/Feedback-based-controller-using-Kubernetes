# Project description:
This project implements a PI controller as a feedback controller for managing a Kubernetes node. The controller dynamically adjusts the MAXPODS count based on the node's CPU utilization, using a discrete linear differential equation modeled with the Black Box technique. The IT infrastructure consists of Kubernetes for container orchestration and Docker for container runtime. Communication between components is facilitated through APIs built with FastAPI, and data collection is performed via Kubernetes APIs. Logging across nodes is managed using Fluent Bit. This project has been tested in a CloudLab environment with the following node specifications: Operating System: Ubuntu 22.04.5 LTS, Memory: 64 GB RAM.

**Outline:**
1. [Model the local controller](#model-the-local-controller)
2. [System Implementation](#system-implementation)
3. [Important Notes](#important-notes)
4. [Installation steps](#installation-steps)
5. [Simulation steps](#simulation-steps)
6. [Logging module](#logging)
7. [Observations](#observations)

## Model the local controller:
First we need to derive the differential equation of pods running in the node vs CPU utilisation:

Loop through a series of jobs, and assign n jobs at a time to a single node. Measure the CPU utilisation using metrics-server API every k intervals of time. Take the average of all k values to find node CPU utilisation for n jobs using moving average filter. Vary n from 1 to the number of jobs where CPU utlisation reaches 100%.

Using linear regression find a and b for the equation y(k+1) = a.y(k) + b.u(k). This equation is the linear differential equation. Through our demo we found out that the equation is y(k+1) = 1.167075452.y(k) + -0.026199928.u(k)

Performance evaluation of the equation is as follows:
RMSE = 0.00000145704328  
R^2 = 0.979831671

Steps to derive the PI controller variables: Now, the goals of the system are as follows - settling time should be 3 sampling times, maximum overshoot should be 10% CPU, which is 0.1. Through pole placement technique, I was able to get Kp and Ki values as follows:

Kp = -3.127  
Ki = 3.1406  

## System Implementation:
The system contains 3 major components as follows:

**The Global controller:**  
It runs in the master node. The global controller fetches jobs periodically and assigns them to the 3 local controllers. It measures the cluster-wide CPU utilisation, and if it is over 80% (which is our reference input), it joins a new node to the cluster. It also has the capability to spin down unnecessary and inactive nodes, thus saving cost of the additional node.

**Local controllers:**  
An instance of local cotnroller runs on each node. A local controller is used to measure the node CPU utilisation periodically, and vary the MAXPODS using the PI controller. At a given time, a node can allow only MAXPODS workloads. It will reject all further jobs.

**Middleware:**  
It is the control center of the system, which exposes several APIs for both the controllers. It uses the Kubernetes APIs to measure node CPU utilisation, cluster wide CPU utilisation, number of active nodes, number of pods running in a cluster, etc.

## Important Notes:
1. This project is designed to be used for 3 nodes. If more nodes are required make necessary changes in global_controller.py  
2. Nodes will be called as node0, node1 and node2. Node0 is the master node and node1 and node2 are worker nodes. To run pods within the master node remove the blocking taint  

## Installation steps:
Clone the repo in all three nodes. To install the pre-requisites, run the makefile on all the nodes.

In the master node, initialise the Kubernetes cluster by running the "kubeadm init" command.

**Install callico**  
Callico is needed to provide secure network connectivity among the nodes. Install by running the following command:  
`kubectl apply -f https://raw.githubusercontent.com/coreos/flannel/master/Documentation/kube-flannel.yml --validate=false`

**Install metrics-server:**  
metrics-server is needed to fetch resource usage monitoring (CPU, memory) details for Kubernetes nodes. Install by running the following command:  
`kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml --validate=false`

## Simulation steps:
**Step 1: start the middleware**  
Run the following command on master node:  
`uvicorn middleware:app --host 0.0.0.0 --port 6666`

**Step 2: start the local controllers**  
Run the following commands in node0, node1 and node2 respectively:  
`python3 local_controller.py 0`  
`python3 local_controller.py 1`  
`python3 local_controller.py 2`

**Step 3: start the global controller**  
node10: `python3 global_controller.py`

## Logging:
Logging is a crucial part of any server architecture. Fluent-bit is used here to collect logs from each node. Following are the installation steps:  

**Install helm:**  
`curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3`
`$ chmod 700 get_helm.sh`
`$ ./get_helm.sh`

**Install fluent-bit:**  
`helm repo add fluent https://fluent.github.io/helm-charts`
`helm upgrade --install fluent-bit fluent/fluent-bit`

**Setup new namespace and start the logging pods:**  
`kubectl create namespace logging`  
`kubectl apply -f fluent-bit-config.yaml`
`kubectl apply -f fluent-bit-daemonset.yaml`

**Check deployment:**  
`kubectl get pods -n logging`

**Get logs:**  
`sudo kubectl logs -n logging [Pod name, like fluent-bit-xxx]`

## Observations:
Using the PI controller, I was able to bring the system closer to the reference input over time. I was able to simulate the following:
1. The Local Controller increases and decreases the value of MAX_PODS  
2. When CPU utilisation goes up, the Global Controller joins the cluster  
3. When all jobs in a node are completed, the Global Controller removes that node from the cluster, making it as a hot-standby node  

**CPU vs Time graph:**  
![CPU vs Time graph](https://github.com/harshgupta6789/Feedback-based-controller-using-Kubernetes/blob/master/CPU%20vs%20Time%20graph.png)

**No. of nodes vs Time graph:**  
![No of nodes vs Time graph](https://github.com/harshgupta6789/Feedback-based-controller-using-Kubernetes/blob/master/No%20of%20nodes%20vs%20Time%20graph.png)
