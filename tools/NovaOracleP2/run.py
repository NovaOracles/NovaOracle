import pandas as pd
import os, re, json
import time
from pathlib import Path
from tools import load_persisted_testcase
from bug_detect import BugDetectInterface
from hierarchy_diff import diff_example_dir
from jsontool import extract_bug_record, parse_detector_output
from state_inference import StateInferenceInterface
from concurrent.futures import ThreadPoolExecutor, as_completed
import configparser

config = configparser.ConfigParser()
base_dir = os.path.dirname(os.path.abspath(__file__))
config.read(os.path.join(base_dir, 'config.ini'))

max_workers = 10
data_path = config.get('S', 'data_path')
bug_path = config.get('S', 'bug_path')
state_path = config.get('S', 'state_path', fallback='state_changes')
xml_diff_path = config.get('S', 'xml_diff_path', fallback='xml_diffs')

if not os.path.isabs(data_path):
    data_path = os.path.join(base_dir, data_path)
if not os.path.isabs(bug_path):
    bug_path = os.path.join(base_dir, bug_path)
if not os.path.isabs(state_path):
    state_path = os.path.join(base_dir, state_path)
if not os.path.isabs(xml_diff_path):
    xml_diff_path = os.path.join(base_dir, xml_diff_path)
bugfree_path = os.path.join(base_dir, 'bugfree')

os.makedirs(bug_path, exist_ok=True)
os.makedirs(bugfree_path, exist_ok=True)
os.makedirs(state_path, exist_ok=True)
os.makedirs(xml_diff_path, exist_ok=True)


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


def normalize_id(value):
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def read_json_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json_file(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


datasets = discover_datasets(data_path)

bug_detector = BugDetectInterface()
state_inferencer = StateInferenceInterface()

token_total= []
token_in = []
token_out = []
time_records = []


def build_actual_path(dataset_path, app_name, testid):
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
    with open(action_description_txt_path, "r", encoding="utf-8") as f:
        action_description_list = [
            re.sub(r"Step\d+:", "", line).strip().replace('"', "'")
            for line in f.readlines()
            if line.strip()
        ]

    actual_path = ""
    for step in range(1, step_count + 1):
        actual_path += (
            f'({step}) Page {step}:'
            + page_description_list[step - 1]
            + action_description_list[step - 1]
            + "\n"
        )
    actual_path += f'({step_count + 1}) Page {step_count + 1}:' + page_description_list[step_count]
    return actual_path


def run_hierarchy_diff(dataset_path, app_name, testid):
    hierarchy_root = Path(dataset_path) / "hierarchy_files"
    example_dir = hierarchy_root / str(app_name) / str(testid)

    if not example_dir.is_dir():
        raise FileNotFoundError(f"No hierarchy XML directory found: {example_dir}")

    diff_file = os.path.join(xml_diff_path, f"{testid}.json")
    if os.path.exists(diff_file):
        return read_json_file(diff_file)

    diff_data = diff_example_dir(example_dir, hierarchy_root)
    write_json_file(diff_file, diff_data)
    return diff_data


def get_state_changes(dataset_path, app_name, testid, stitch_image_path, actual_path):
    output_file = os.path.join(state_path, f"{testid}.json")
    if os.path.exists(output_file):
        return read_json_file(output_file), 0, 0, 0

    diff_data = run_hierarchy_diff(dataset_path, app_name, testid)
    state_output, token_usage, prompt_tokens, completion_tokens = state_inferencer.get_output(
        stitch_image_path,
        actual_path,
        diff_data,
    )
    parsed = parse_detector_output(state_output)
    state_record = {"state_changes": parsed.get("state_changes", [])}
    write_json_file(output_file, state_record)
    return state_record, token_usage, prompt_tokens, completion_tokens


def process_testcase(dataset_name, dataset_path, row):
    testcase = row['TestCase']
    if pd.isna(testcase):
        return None
    testid = normalize_id(row['ID'])
    app_name = row['AppName']
    output_path = bugfree_path if dataset_name == 'BugFree' else bug_path
    output_file = os.path.join(output_path, f'BugReport_{app_name}_{testid}.json')
    if os.path.exists(output_file):
        return None
    print(f"Dataset: {dataset_name}, Appname: {app_name}, Test ID: {testid}")

    stitch_path = os.path.join(dataset_path, 'images', 'stitch_images')
    actual_path = build_actual_path(dataset_path, app_name, testid)

    stitch_image_path = os.path.join(stitch_path, app_name, f"{testid}.jpg")

    #bug detector
    start_time = time.perf_counter()
    state_record, state_token_usage, state_prompt_tokens, state_completion_tokens = get_state_changes(
        dataset_path,
        app_name,
        testid,
        stitch_image_path,
        actual_path,
    )
    bug_output, bug_token_usage, bug_prompt_tokens, bug_completion_tokens = bug_detector.get_output(
        stitch_image_path,
        actual_path,
        state_record,
    )
    parsed = parse_detector_output(bug_output)
    bug = extract_bug_record(parsed)
    write_json_file(output_file, bug)
    token_usage = state_token_usage + bug_token_usage
    prompt_tokens = state_prompt_tokens + bug_prompt_tokens
    completion_tokens = state_completion_tokens + bug_completion_tokens
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
