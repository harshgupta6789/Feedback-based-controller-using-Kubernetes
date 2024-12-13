import time
from node import Node
import middleware
import random

def parse_args(job):
    elements = job.split()
    pairs = [(elements[i], elements[i + 1]) for i in range(1, len(elements), 2)]
    formatted_output = ', '.join(f'"{key}", "{value}"' for key, value in pairs)
    return formatted_output

def read_jobs(file_path):
    """
    Reads jobs from the specified file and returns a list of job commands.
    """
    jobs = []
    try:
        with open(file_path, 'r') as f:
            for line in f:
                job = line.strip()
                if job and not job.startswith('#'):
                    jobs.append(job)
        print(f"Loaded {len(jobs)} jobs from {file_path}.")
    except FileNotFoundError:
        print(f"Jobs file '{file_path}' not found.")
    return jobs

def main(no_of_pods):
    
    # Initialize nodes
    node1 = Node("node1", "node1.harshproject.ufl-eel6871-fa24-pg0.utah.cloudlab.us")

    # activate node1
    # system will be modelled on the basis of a single node, which is node1. Same model will be used for node0 and node1, since all nodes are identical
    print("Initialized 1 nodes")

    # Read jobs
    jobs = read_jobs("jobs_for_modelling.txt")
    if not jobs:
        print("No jobs to assign. Exiting.")
        return

    current_job_count = 0
    while True:
        if current_job_count >= no_of_pods:
            print("All jobs have been assigned.")
            break

        # select a random job from the list of jobs
        current_job_index = random.randint(0, len(jobs) - 1)

        job = jobs[current_job_index]

        # remove the job chosen to avoid duplicate jobs
        jobs.pop(current_job_index)

        print(f"Assigning job {current_job_count + 1}: {job}")
        job = parse_args(job)
        result = middleware.add_pod(node1, job)

        if result:
            current_job_count += 1
            print(f"Job {current_job_count} assigned successfully.")
        else:
            print(f"Failed to assign job {current_job_count + 1}. Retrying...")

        time.sleep(2)  # Wait for 5 seconds before assigning the next job

    print("Job assignment process completed. Check metrics server output for CPU utilisation")

if __name__ == "__main__":
    no_of_pods = int(input("Enter number of jobs: "))
    main(no_of_pods)
