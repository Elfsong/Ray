# coding: utf-8

# Author: Du Mingzhe (mingzhe@nus.edu.sg)
# Date: 2025-05-27

import os
import json
import string
import random
import subprocess
from tqdm import tqdm
from multiprocessing import Pool
from tqdm.contrib.concurrent import process_map

toml_template = """
[cosmic-ray]
module-path = "data/mods/test_{mod_name}.py"
timeout = {timeout}
excluded-modules = []
test-command = "pytest data/mods/test_{mod_name}.py"

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

def generate_alphabetic_uuid(length=32):
    return ''.join(random.choices(string.ascii_letters, k=length))

# Initialization 
def baseline_init(timeout=1, num_samples=100):
    if not os.path.exists('data/mods'):
        os.makedirs('data/mods')
    else:
        for file in tqdm(os.listdir('data/mods'), desc="[+] 🧹 Cleaning up existing files"):
            os.remove(f'data/mods/{file}')

    data_hander = open('data/TestBench_claude-3-5-haiku-latest.jsonl', 'r')
    raw_data = data_hander.readlines()[:num_samples]

    for line in tqdm(raw_data, desc="[+] 💾 Processing raw data"):
        uuid = generate_alphabetic_uuid(length=16)
        instance = json.loads(line)

        # create 'test_mod'
        with open(f'data/mods/test_{uuid}.py', 'w') as f:
            f.write(code_import)
            f.write(instance['code'])
            test_cases = ''
            for test in instance['tests']:
                test_cases += f'{test}\n\n'
            f.write("\n\n" + "#" * 100 + "\n\n")
            f.write(test_cases)

        # create 'toml'
        with open(f'data/mods/{uuid}.toml', 'w') as f:
            f.write(toml_template.format(mod_name=uuid, timeout=timeout))

def baseline_run():
    total_tasks = list()
    correct_tasks = list()

    for file_name in tqdm(os.listdir('data/mods'), desc="[+] ⏳ Filtering baseline tasks"):
        if file_name.endswith('.toml'):
            total_tasks.append(file_name.split('.')[0])

    for uuid in tqdm(total_tasks, desc="[+] 🔄 Initialize Cosmic-Ray Mutation"):
        # Initialize cosmic-ray
        try:
            subprocess.run(['cosmic-ray', 'init', f'data/mods/{uuid}.toml', f'data/mods/{uuid}.sqlite'], check=True)
        except Exception as e:
            print(f'[-] Initialize Cosmic-Ray Error: {e}')
            continue

        # Run cosmic-ray
        try:
            subprocess.run(['cosmic-ray', 'baseline', f'data/mods/{uuid}.toml'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            correct_tasks.append(uuid)
        except Exception as e:
            # print(f'[-] Run Cosmic-Ray Error: {e}')
            continue
    
    # Save correct tasks
    with open('data/correct_tasks', 'w') as f:
        for task in correct_tasks:
            f.write(f'{task}\n')
    print(f'[+] ✅ Correct tasks: {len(total_tasks)} -> {len(correct_tasks)} (convert rate: {len(correct_tasks) / len(total_tasks)})')

def mutation_run_wrapper(task):
    # cosmic-ray exec tutorial.toml tutorial.sqlite
    # try:
    #     response = subprocess.run(['cr-report', f'data/mods/{task}.sqlite', '--show-pending'], check=True)
    #     print(f"[+] {task}: {response.stdout}")
    # except Exception as e:
    #     print(f'[-] Error: {e}')

    try:
        subprocess.run(['cosmic-ray', 'exec', f'data/mods/{task}.toml', f'data/mods/{task}.sqlite'], check=True)
    except Exception as e:
        print(f'[-] Error: {e}')

def mutation_run():
    correct_tasks = list()
    with open('data/correct_tasks', 'r') as f:
        for line in f.readlines():
            correct_tasks.append(line.strip())

    process_map(mutation_run_wrapper, correct_tasks, desc="[+] 🔮 Running mutations")

if __name__ == "__main__":
    baseline_init(timeout=1, num_samples=20)
    baseline_run()
    mutation_run()
