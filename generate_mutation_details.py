import json
import sqlite3
import os
from tqdm import tqdm

def main(base_dir):
    results = []
    for task_dir in tqdm(os.listdir(base_dir)):
        if not task_dir.startswith("task_"):
            continue

        task_id = task_dir.split("_")[1]
        db_path = os.path.join(base_dir, task_dir, "cosmic-ray.sqlite")
        code_path = os.path.join(base_dir, task_dir, "mod.py")

        if not os.path.exists(db_path) or not os.path.exists(code_path):
            continue

        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT job_id, operator_name, start_pos_row, start_pos_col, end_pos_row, end_pos_col FROM mutation_specs")
            mutations = cursor.fetchall()

            cursor.execute("SELECT job_id, test_outcome, diff FROM work_results")
            work_results = {row[0]: {"test_outcome": row[1], "diff": row[2]} for row in cursor.fetchall()}

            with open(code_path, "r") as f:
                code = f.read()

            mutants_list = []
            for job_id, operator_name, start_row, start_col, end_row, end_col in mutations:
                status = work_results.get(job_id, {}).get("test_outcome", "pending")
                diff = work_results.get(job_id, {}).get("diff", "No diff")

                mutants_list.append({
                    "status": status,
                    "mutation_operator": operator_name,
                    "mutation_diff": diff,
                    "start_line": start_row,
                    "start_column": start_col,
                    "end_line": end_row,
                    "end_column": end_col,
                })

            results.append({
                "task_id": task_id,
                "original_code": code,
                "mutants": mutants_list
            })

    with open("new_mutation_details.jsonl", "w") as f:
        for result in results:
            f.write(json.dumps(result) + "\n")


if __name__ == "__main__":
    base_dir = "/home/nus_cisco_wp1/Projects/Ray/data/testbench/mutation_5/TestBench_datasetv6"
    main(base_dir)
