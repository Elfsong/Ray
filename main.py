# coding: utf-8

# Author: Du Mingzhe (mingzhe@nus.edu.sg)
# Date: 2025-05-27

import re
import os
import json
import string
import random
import shutil
import tempfile
import datetime
import subprocess
from tqdm import tqdm
from multiprocessing import Pool
from tqdm.contrib.concurrent import process_map

toml_template = """
[cosmic-ray]
module-path = "test.py"
timeout = {timeout}
excluded-modules = []
test-command = "pytest test.py"

[cosmic-ray.distributor]
name = "local"
"""

code_import = """
import os
import re
import math
import numpy
import pandas
import pytest
import random
import string
import warnings
import datetime
import traceback
import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional, Union, Tuple, Set, FrozenSet, Sequence, Iterable, Generator, Callable
"""

def rename_test_functions(test_code):
    test_counter = 0
    new_lines = list()
    pattern = re.compile(r"(\s*def\s+)(test_)(.*)")
    test_code_lines = test_code.split('\n')
    
    for line in test_code_lines:
        match = pattern.match(line)
        if match:
            test_counter += 1
            new_lines.append(f"{match.group(1)}test_{test_counter}_{match.group(3)}")
        else:
            new_lines.append(line)
    
    return '\n'.join(new_lines)

def parse_pytest_output(output: str) -> dict:
    """
    Parses the stdout of a `pytest --cov` run to extract key metrics.

    Args:
        output: The string output from the pytest command.

    Returns:
        A dictionary containing test results and coverage.
    """
    # 🎯 Default values
    total_coverage = 0
    passed_count = 0
    failed_count = 0

    # Regex to find the total coverage percentage from the 'TOTAL' line
    coverage_match = re.search(r"^TOTAL\s+.*\s+(\d+)%$", output, re.MULTILINE)
    if coverage_match:
        total_coverage = int(coverage_match.group(1))

    # Regex to find the numbers in the final summary line
    # e.g., "===... 4 failed, 1 passed in 9.85s ...==="
    summary_line_match = re.search(
        r"=+ (.*) in .*s =+", output
    )
    if summary_line_match:
        summary_text = summary_line_match.group(1)
        
        passed_match = re.search(r"(\d+)\s+passed", summary_text)
        if passed_match:
            passed_count = int(passed_match.group(1))
            
        failed_match = re.search(r"(\d+)\s+failed", summary_text)
        if failed_match:
            failed_count = int(failed_match.group(1))

    # --- Calculations ---
    total_tests = passed_count + failed_count
    pass_rate = 0.0
    if total_tests > 0:
        pass_rate = (passed_count / total_tests) * 100

    return {
        "total_coverage_percent": total_coverage,
        "pass_rate_percent": round(pass_rate, 2),
        "passed_tests": passed_count,
        "failed_tests": failed_count,
        "total_tests": total_tests,
    }

# Initialization 
def cosmic_ray_init(model_generation_file, timeout=1, num_samples=100):
    model_name = model_generation_file.split('/')[-1].split('.')[0]

    if os.path.exists(f'data/mods/{model_name}'):
        print(f"[+] 🧹 Cleaning up existing files in {model_name}...")
        shutil.rmtree(f'data/mods/{model_name}')
    print(f"[+] 📂 Creating new directory {model_name}...")
    os.makedirs(f'data/mods/{model_name}')

    data_hander = open(model_generation_file, 'r')
    
    # parse the data
    # raw_data = data_hander.readlines()[:num_samples]
    raw_data = json.loads(data_hander.read())[:num_samples]

    for idx, instance in tqdm(enumerate(raw_data), desc="[+] 💾 Processing raw data"):
        os.makedirs(f'data/mods/{model_name}/task_{idx}')

        with open(f'data/mods/{model_name}/task_{idx}/test.py', 'w') as f:
            test_code = ''
            test_code += code_import + '\n\n'
            test_code += instance['code'] + '\n\n'
            test_cases = ''
            for test in instance['tests']:
                test_cases += f'{test}\n\n'
            test_code += "\n\n" + "#" * 100 + "\n\n"
            test_code += test_cases
            
            test_code = rename_test_functions(test_code)
            f.write(test_code)

        # create 'toml'
        with open(f'data/mods/{model_name}/task_{idx}/cosmic-ray.toml', 'w') as f:
            f.write(toml_template.format(model_name=model_name, task_id=idx, timeout=timeout))

def cosmic_ray_setup(model_generation_file):
    model_name = model_generation_file.split('/')[-1].split('.')[0]
    total_tasks = list()
    correct_tasks = list()

    for file_name in tqdm(os.listdir(f'data/mods/{model_name}'), desc="[+] ⏳ Filtering baseline tasks"):
        if file_name.startswith('task_'):
            total_tasks.append(file_name)

    for task_id in tqdm(total_tasks, desc="[+] 🔄 Initialize Cosmic-Ray Mutation"):
        working_dir = f'data/mods/{model_name}/{task_id}'
        
        # Initialize cosmic-ray
        try:
            subprocess.run(['cosmic-ray', 'init', 'cosmic-ray.toml', 'cosmic-ray.sqlite'], cwd=working_dir, check=True)
        except Exception as e:
            print(f'[-] Initialize Cosmic-Ray Error: {e}')
            continue

        # Run cosmic-ray
        try:
            # subprocess.run(['cosmic-ray', 'baseline', f'data/mods/{model_name}/{task_id}.toml'], check=True)
            subprocess.run(['cosmic-ray', 'baseline', 'cosmic-ray.toml'], cwd=working_dir, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            correct_tasks.append(task_id)
            print(f"[+] Correct task - {task_id}")
        except Exception as e:
            print(f'[-] Run Cosmic-Ray Error: {e}')
            continue
    
    # Save correct tasks
    with open(f'data/correct_tasks_{model_name}', 'w') as f:
        for task in correct_tasks:
            f.write(f'{task}\n')
    print(f'[+] ✅ Correct tasks: {len(total_tasks)} -> {len(correct_tasks)} (convert rate: {len(correct_tasks) / len(total_tasks)})')

def cosmic_ray_status(model_name, task):
    try:
        response = subprocess.run(['cr-report', f'data/mods/{model_name}/{task}/cosmic-ray.sqlite', '--show-pending'], check=True, capture_output=True, text=True)
    except Exception as e:
        print(f'[-] Error: {e}')
        return False
    
    total_jobs_match = re.search(r"total jobs:\s*(\d+)", response.stdout)
    completed_jobs_match = re.search(r"complete:\s*(\d+)\s*\(", response.stdout)

    if total_jobs_match and completed_jobs_match:
        total_jobs_number = int(total_jobs_match.group(1))
        completed_jobs_number = int(completed_jobs_match.group(1))
        # print(f"[+] Task {task}: Total jobs: {total_jobs_number}, Completed jobs: {completed_jobs_number}")
        if total_jobs_number == 0: return True
        return completed_jobs_number == total_jobs_number
    else:
        return False

def mutation_run_wrapper(model_name, task):
    # cosmic-ray exec tutorial.toml tutorial.sqlite
    completed = cosmic_ray_status(model_name, task)
    if completed: return
    print(f"[+] Task {task}: Running mutations")
    
    working_dir = f'data/mods/{model_name}/{task}'
    try:
        subprocess.run(['cosmic-ray', 'exec', f'cosmic-ray.toml', f'cosmic-ray.sqlite'], cwd=working_dir, check=True, timeout=120)
    except Exception as e:
        print(f'[-] Error: {e}')

def mutation_run(model_generation_file):
    model_name = model_generation_file.split('/')[-1].split('.')[0]
    correct_tasks = list()
    with open(f'data/correct_tasks_{model_name}', 'r') as f:
        for line in f.readlines():
            correct_tasks.append(line.strip())
            
    print(f'[+] ⏱️ Start time: {datetime.datetime.now()}')
    process_map(mutation_run_wrapper, [model_name]*len(correct_tasks), correct_tasks, desc="[+] 🔮 Running mutations", max_workers=1)
    print(f'[+] ⏱️ End time: {datetime.datetime.now()}')

def pytest_run_wrapper(task_pair):
    model_name, task_id = task_pair
    test_file_path = f'data/mods/{model_name}/{task_id}/test.py'
    source_code_path = f'data/mods/{model_name}/{task_id}'
    try:
        # temporary dictionary to execute pytest
        with tempfile.TemporaryDirectory() as temp_dir:
            abs_test_file_path = os.path.abspath(test_file_path)
            abs_source_code_path = os.path.abspath(source_code_path)
            result = subprocess.run(['pytest', abs_test_file_path, f'--cov={abs_source_code_path}', '--cov-branch'], cwd=temp_dir, capture_output=True, text=True, timeout=30)
            result_dict = parse_pytest_output(result.stdout)
        return {'model_name': model_name, 'task': task_id, 'result': result_dict, "status": "success"}
    except Exception as e:
        return {'model_name': model_name, 'task': task_id, 'result': None, "status": "error"}

def pytest_run(model_name):
    tasks = list()
    
    for task in os.listdir(f'data/mods/{model_name}'):
        if task.startswith('task_'):
            tasks.append((model_name, task))
            
    results = process_map(pytest_run_wrapper, tasks, desc="[+] 🔄 Running pytest", chunksize=1)
    
    with open(f'data/mods/{model_name}/results.jsonl', 'w') as f:
        for result in results:
            f.write(json.dumps(result) + '\n')


if __name__ == "__main__":
    model_generation_file_path = "data/results/datasetv3.jsonl"
    cosmic_ray_init(model_generation_file_path, timeout=2, num_samples=10000)
    cosmic_ray_setup(model_generation_file_path)
    mutation_run(model_generation_file_path)
