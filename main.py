# coding: utf-8

# Author: Du Mingzhe (mingzhe@nus.edu.sg)
# Date: 2025-05-27

import re
import os
import json
import string
import random
import shutil
import datetime
import subprocess
from tqdm import tqdm
from multiprocessing import Pool
from tqdm.contrib.concurrent import process_map

toml_template = """
[cosmic-ray]
module-path = "data/mods/{model_name}/test_{mod_name}.py"
timeout = {timeout}
excluded-modules = []
test-command = "pytest data/mods/{model_name}/test_{mod_name}.py"

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

# Initialization 
def cosmic_ray_init(model_generation_file, timeout=1, num_samples=100):
    model_name = model_generation_file.split('/')[-1].split('.')[0]

    if os.path.exists(f'data/mods/{model_name}'):
        print(f"[+] 🧹 Cleaning up existing files in {model_name}...")
        shutil.rmtree(f'data/mods/{model_name}')
    print(f"[+] 📂 Creating new directory {model_name}...")
    os.makedirs(f'data/mods/{model_name}')

    data_hander = open(model_generation_file, 'r')
    raw_data = data_hander.readlines()[:num_samples]

    for idx, line in tqdm(enumerate(raw_data), desc="[+] 💾 Processing raw data"):
        instance = json.loads(line)

        with open(f'data/mods/{model_name}/test_{idx}.py', 'w') as f:
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
        with open(f'data/mods/{model_name}/{idx}.toml', 'w') as f:
            f.write(toml_template.format(model_name=model_name, mod_name=idx, timeout=timeout))

def cosmic_ray_setup(model_generation_file):
    model_name = model_generation_file.split('/')[-1].split('.')[0]
    total_tasks = list()
    correct_tasks = list()

    for file_name in tqdm(os.listdir(f'data/mods/{model_name}'), desc="[+] ⏳ Filtering baseline tasks"):
        if file_name.endswith('.toml'):
            total_tasks.append(file_name.split('.')[0])

    for task_id in tqdm(total_tasks, desc="[+] 🔄 Initialize Cosmic-Ray Mutation"):
        # Initialize cosmic-ray
        try:
            subprocess.run(['cosmic-ray', 'init', f'data/mods/{model_name}/{task_id}.toml', f'data/mods/{model_name}/{task_id}.sqlite'], check=True)
        except Exception as e:
            print(f'[-] Initialize Cosmic-Ray Error: {e}')
            continue

        # Run cosmic-ray
        try:
            # subprocess.run(['cosmic-ray', 'baseline', f'data/mods/{model_name}/{task_id}.toml'], check=True)
            subprocess.run(['cosmic-ray', 'baseline', f'data/mods/{model_name}/{task_id}.toml'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            correct_tasks.append(task_id)
            print(f"[+] Correct task - {task_id}")
        except Exception as e:
            # print(f'[-] Run Cosmic-Ray Error: {e}')
            continue
    
    # Save correct tasks
    with open(f'data/correct_tasks_{model_name}', 'w') as f:
        for task in correct_tasks:
            f.write(f'{task}\n')
    print(f'[+] ✅ Correct tasks: {len(total_tasks)} -> {len(correct_tasks)} (convert rate: {len(correct_tasks) / len(total_tasks)})')

def cosmic_ray_status(model_name, task):
    try:
        response = subprocess.run(['cr-report', f'data/mods/{model_name}/{task}.sqlite', '--show-pending'], check=True, capture_output=True, text=True)
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
    completed = get_completed_tasks(model_name, task)
    if completed: return
    print(f"[+] Task {task}: Running mutations")
    
    try:
        subprocess.run(['cosmic-ray', 'exec', f'data/mods/{model_name}/{task}.toml', f'data/mods/{model_name}/{task}.sqlite'], check=True)
    except Exception as e:
        print(f'[-] Error: {e}')

def mutation_run(model_generation_file):
    model_name = model_generation_file.split('/')[-1].split('.')[0]
    correct_tasks = list()
    with open(f'data/correct_tasks_{model_name}', 'r') as f:
        for line in f.readlines():
            correct_tasks.append(line.strip())
            
    print(f'[+] ⏱️ Start time: {datetime.datetime.now()}')
    process_map(mutation_run_wrapper, model_name, correct_tasks, desc="[+] 🔮 Running mutations")
    print(f'[+] ⏱️ End time: {datetime.datetime.now()}')

def pytest_run(model_name):
    for task in tqdm(os.listdir(f'data/mods/{model_name}'), desc="[+] 🔄 Running pytest"):
        if task.endswith('.py'):
            subprocess.run(['pytest', f'data/mods/{model_name}/{task}'], check=True)

if __name__ == "__main__":
    model_generation_folder = "/home/nus_cisco_wp1/Projects/Ray/data/results"
    for model_generation_file in os.listdir(model_generation_folder):
        model_generation_file_path = os.path.join(model_generation_folder, model_generation_file)
        if model_generation_file_path.endswith('.jsonl'):
            model_name = model_generation_file_path.split('/')[-1].split('.')[0]
            cosmic_ray_init(model_generation_file_path, timeout=2, num_samples=100000)
            # cosmic_ray_setup(model_generation_file_path)
            
        print("================================================")

