import pandas as pd
import os, json
import time
from bug_detect import BugDetectInterface
from jsontool import extract_bug_record, parse_detector_output
from concurrent.futures import ThreadPoolExecutor, as_completed
import configparser

config = configparser.ConfigParser()
base_dir = os.path.dirname(os.path.abspath(__file__))
config.read(os.path.join(base_dir, 'config.ini'))

max_workers = 10
data_path = config.get('S', 'data_path')
bug_path = config.get('S', 'bug_path')

if not os.path.isabs(data_path):
    data_path = os.path.join(base_dir, data_path)
if not os.path.isabs(bug_path):
    bug_path = os.path.join(base_dir, bug_path)
bugfree_path = os.path.join(base_dir, 'bugfree')

os.makedirs(bug_path, exist_ok=True)
os.makedirs(bugfree_path, exist_ok=True)


def first_existing_path(*paths):
    for path in paths:
        if os.path.exists(path):
            return path
    return None


def discover_datasets(root_path):
    datasets = []
    for name in sorted(os.listdir(root_path)):
        candidate_path = os.path.join(root_path, name)
        if os.path.isdir(candidate_path):
            datasets.append((name, candidate_path))

    if not datasets:
        dataset_name = os.path.basename(os.path.normpath(root_path))
        return [(dataset_name, root_path)]

    return datasets


datasets = discover_datasets(data_path)
bug_detector = BugDetectInterface()

token_total= []
token_in = []
token_out = []
time_records = []

def process_testcase(dataset_name, dataset_path, row):
    testcase = row['TestCase']
    if pd.isna(testcase):
        return None
    testid = row['ID']
    app_name = row['AppName']
    output_path = bugfree_path if dataset_name == 'BugFree' else bug_path
    output_file = os.path.join(output_path, f'BugReport_{app_name}_{testid}.json')
    if os.path.exists(output_file):
        return None
    print(f"Dataset: {dataset_name}, Appname: {app_name}, Test ID: {testid}")

    stitch_path = os.path.join(dataset_path, 'images', 'stitch_images')
    stitch_image_path = os.path.join(stitch_path, app_name, f"{testid}.jpg")

    #bug detector
    start_time = time.perf_counter()
    bug_output, bug_token_usage, bug_prompt_tokens, bug_completion_tokens = bug_detector.get_output(stitch_image_path)
    parsed = parse_detector_output(bug_output)
    bug = extract_bug_record(parsed)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(bug, f, ensure_ascii=False, indent=4)
    token_usage = bug_token_usage
    prompt_tokens = bug_prompt_tokens
    completion_tokens = bug_completion_tokens
    token_total.append(token_usage)
    token_in.append(prompt_tokens)
    token_out.append(completion_tokens)
    end_time = time.perf_counter()
    time_records.append(end_time - start_time)


with ThreadPoolExecutor(max_workers=max_workers) as executor:
    futures = {}
    for dataset_name, dataset_path in datasets:
        testcase_path = first_existing_path(
            os.path.join(dataset_path, 'test_case', 'test_case.csv'),
            os.path.join(dataset_path, 'test_case', 'no_bug_case.csv'),
        )
        if testcase_path is None:
            print(f"Loaded dataset: {dataset_name}, test cases: 0")
            continue
        testcase_file = pd.read_csv(testcase_path, header=0)
        print(f"Loaded dataset: {dataset_name}, test cases: {len(testcase_file)}")
        for idx, row in testcase_file.iterrows():
            future = executor.submit(process_testcase, dataset_name, dataset_path, row)
            futures[future] = f"{dataset_name}:{idx}"

    for future in as_completed(futures):
        try:
            result = future.result()
        except Exception as e:
            print(f"task {futures[future]} failed: {e}")

with open(os.path.join(base_dir, 'token_usage.txt'), 'a') as f:
    for num in token_total:
        f.write(str(num) + '\n')
with open(os.path.join(base_dir, 'token_in_usage.txt'), 'a') as f:
    for num in token_in:
        f.write(str(num) + '\n')
with open(os.path.join(base_dir, 'token_out_usage.txt'), 'a') as f:
    for num in token_out:
        f.write(str(num) + '\n')
with open(os.path.join(base_dir, "times_records.txt"), "a") as f:
    for t in time_records:
        f.write(f"{t}\n")
