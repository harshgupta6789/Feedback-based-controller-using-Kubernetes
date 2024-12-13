import subprocess

try:
    # remove all log files
    print(f"Removing log files")
    result = subprocess.run(["rm", "-f", "logfile.log"], check=True)
    command = f"kubectl delete pods -n default"
    result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    print(f"Log files removed")

    # delete all pods
    print("deleting all pods")
    command = f"kubectl delete pods --all"
    result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    print("all pods deleted")

    # remove all nodes: node1 and node2
    print("deleting node1")
    command = f"kubectl delete node node1.harshproject.ufl-eel6871-fa24-pg0.utah.cloudlab.us"
    result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    print("node1 deleted")

    print("deleting node2")
    command = f"kubectl delete node node2.harshproject.ufl-eel6871-fa24-pg0.utah.cloudlab.us"
    result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    print("node2 deleted")
except:
    print(f"Error while deleting pods and logs")
print(f"Cleanup successful")