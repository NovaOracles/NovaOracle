import pandas as pd
import os, re, json
import time
from tools import load_persisted_testcase
from func_interface import FuncInterface
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

func_generator = FuncInterface()
bug_detector = BugDetectInterface()

token_total= []
token_in = []
token_out = []
time_records = []


def get_function_field(function_dict, field_name, aliases):
    for key in aliases:
        value = function_dict.get(key)
        if value:
            return value

    available_keys = ', '.join(function_dict.keys())
    raise KeyError(f"Missing {field_name}. Available keys: {available_keys}")


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
    structcase_path = os.path.join(dataset_path, 'struct_case_data')
    action_desc_path = first_existing_path(
        os.path.join(dataset_path, 'action_description_data'),
        os.path.join(dataset_path, 'action_description_path'),
    )
    if action_desc_path is None:
        raise FileNotFoundError(f"No action description directory found under: {dataset_path}")
    page_desc_path = os.path.join(dataset_path, 'page_description_data')

    persist_path = os.path.join(structcase_path, app_name, f"{testid}.pkl")
    test_case_list = load_persisted_testcase(persist_path)
    if test_case_list is None:
        raise FileNotFoundError(f"No persisted test case list found: {persist_path}")
    step_count = len(test_case_list)

    page_description_txt_path = os.path.join(page_desc_path, app_name, f"{testid}.txt")
    with open(page_description_txt_path, "r", encoding="utf-8") as f:
        page_description_list = [line.strip().replace('"', "'") for line in f.readlines() if line.strip()]

    action_description_txt_path = os.path.join(action_desc_path, app_name, f"{testid}.txt")
    with (open(action_description_txt_path, "r", encoding="utf-8") as f):
        action_description_list = [re.sub(r"Step\d+:", "", line).strip().replace('"', "'") for line in f.readlines() if line.strip()]

    actual_path = ""
    for step in range(1, step_count + 1):
        actual_path +=  f'({step}) Page {step}:' + page_description_list[step - 1] + action_description_list[step - 1] + "\n"
    actual_path += f'({step_count + 1}) Page {step_count + 1}:' + page_description_list[step_count]

    stitch_image_path = os.path.join(stitch_path, app_name, f"{testid}.jpg")

    function, func_token_usage, func_prompt_tokens, func_completion_tokens = func_generator.get_output(actual_path)
    function_dict = json.loads(function)
    function_name = get_function_field(
        function_dict,
        'function_name',
        ['function_name', 'Function name', 'Function Name', 'name'],
    )
    function_description = get_function_field(
        function_dict,
        'function_description',
        ['function_description', 'Function description', 'Function Description', 'description'],
    )
    function_goal = get_function_field(
        function_dict,
        'function_goal',
        ['function_goal', 'Function goal', 'Function Goal', 'goal'],
    )

    #bug detector
    start_time = time.perf_counter()
    bug_output, bug_token_usage, bug_prompt_tokens, bug_completion_tokens = bug_detector.get_output(stitch_image_path, function_name, function_description, function_goal, actual_path)
    parsed = parse_detector_output(bug_output)
    bug = extract_bug_record(parsed)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(bug, f, ensure_ascii=False, indent=4)
    token_usage = func_token_usage + bug_token_usage
    prompt_tokens = func_prompt_tokens + bug_prompt_tokens
    completion_tokens = func_completion_tokens + bug_completion_tokens
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
