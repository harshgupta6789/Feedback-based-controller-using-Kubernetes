import requests
import logging
import time

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

def main(file_name):
    # Read jobs
    jobs = read_jobs(file_name)
    if not jobs:
        print("No jobs to assign. Exiting.")
        return

    current_job_count = 0
    while True:
        if current_job_count >= len(jobs):
            print("All jobs have been assigned.")
            break
        try:
            r = requests.post('http://127.0.0.1:6668/assign_jobs_api')
            current_job_count += 1
        except Exception as e:
            print(f"Error occured: ", e)
        time.sleep(15)
        
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        filename='extra_credit_logfile.log'
    )
    file_name = input("Enter file name: ")
    main(file_name)