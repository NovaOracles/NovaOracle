import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import configparser
import pandas as pd

from compare_images import compare_images
from function_identification import FunctionIdentification
from jsontool import extract_bug_record, parse_detector_output
from response_verification import ResponseVerification
from tools import load_persisted_testcase


config = configparser.ConfigParser()
base_dir = os.path.dirname(os.path.abspath(__file__))
config.read(os.path.join(base_dir, 'config.ini'))

max_workers = 10
data_path = config.get('S', 'data_path')
bug_path = config.get('S', 'bug_path')

if not os.path.isabs(data_path):
    data_path = os.path.abspath(os.path.join(base_dir, data_path))
if not os.path.isabs(bug_path):
    bug_path = os.path.abspath(os.path.join(base_dir, bug_path))
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


def has_complete_output(output_file):
    if not os.path.exists(output_file):
        return False
    try:
        with open(output_file, "r", encoding="utf-8") as f:
            existing_output = json.load(f)
    except (OSError, json.JSONDecodeError):
        return False

    return existing_output.get("confidence") is not None


datasets = discover_datasets(data_path)

func_iden = FunctionIdentification()
response_ver = ResponseVerification()
token_statis = []
token_in = []
token_out = []
time_records = []


def get_bool_field(parsed, *keys, default=False):
    for key in keys:
        value = parsed.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {'true', 'yes', '1'}:
                return True
            if normalized in {'false', 'no', '0'}:
                return False
    return default


def get_float_field(parsed, *keys, default=None):
    for key in keys:
        value = parsed.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, str):
            normalized = value.strip().rstrip('%')
            try:
                confidence = float(normalized)
            except ValueError:
                continue
            if value.strip().endswith('%'):
                confidence = confidence / 100
            return confidence
    return default


def build_response_step(step_id, parsed, component_function):
    judgement = get_bool_field(
        parsed,
        'judgement',
        'judgment',
        'meets_expectation',
        default=not bool(parsed.get('bug_found', False)),
    )
    return {
        "judgement": judgement,
        "reason": parsed.get("reason", parsed.get("bug_description", "")),
        "step_id": step_id,
        "func_iden": component_function,
    }


def build_non_response_step(step_id):
    return {
        "judgement": False,
        "reason": "non-response bug",
        "step_id": step_id,
    }


def build_bug_record(evidence_steps, confidence_by_step):
    failed_steps = [step for step in evidence_steps if not step.get("judgement", True)]

    if failed_steps:
        first_bug = failed_steps[0]
        first_bug_reason = first_bug.get("reason", "")
        first_bug_confidence = confidence_by_step.get(first_bug.get("step_id"))
        detector_like_output = {
            "bug_found": True,
            "bug_type": "missing_effect" if first_bug_reason == "non-response bug" else "other",
            "bug_page_step": first_bug.get("step_id"),
            "bug_description": first_bug_reason,
            "confidence": first_bug_confidence,
            "step_analysis": evidence_steps,
            "exploration_feedback": [],
        }
    else:
        valid_confidences = [
            confidence_by_step[step["step_id"]]
            for step in evidence_steps
            if step.get("step_id") in confidence_by_step
        ]
        detector_like_output = {
            "bug_found": False,
            "bug_type": "none",
            "bug_page_step": 0,
            "bug_description": "No bug found.",
            "confidence": min(valid_confidences) if valid_confidences else None,
            "step_analysis": evidence_steps,
            "exploration_feedback": [],
        }

    return extract_bug_record(detector_like_output)


def process_testcase(dataset_name, dataset_path, row):
    testcase = row['TestCase']
    if pd.isna(testcase):
        return None

    testid = row['ID']
    app_name = row['AppName']
    output_path = bugfree_path if dataset_name == 'BugFree' else bug_path
    output_file = os.path.join(output_path, f'BugReport_{app_name}_{testid}.json')
    if has_complete_output(output_file):
        return None

    print(f"Dataset: {dataset_name}, Appname: {app_name}, Test ID: {testid}")

    images_path = os.path.join(dataset_path, 'images', 'screenshots')
    anno_image_path = os.path.join(dataset_path, 'images', 'annotated_images')
    structcase_path = os.path.join(dataset_path, 'struct_case_data')
    action_desc_path = first_existing_path(
        os.path.join(dataset_path, 'action_description_data'),
        os.path.join(dataset_path, 'action_description_path'),
    )
    if action_desc_path is None:
        raise FileNotFoundError(f"No action description directory found under: {dataset_path}")

    persist_path = os.path.join(structcase_path, app_name, f"{testid}.pkl")
    test_case_list = load_persisted_testcase(persist_path)
    if test_case_list is None:
        raise FileNotFoundError(f"No persisted test case list found: {persist_path}")
    step_count = len(test_case_list)

    action_description_txt_path = os.path.join(action_desc_path, app_name, f"{testid}.txt")
    with open(action_description_txt_path, "r", encoding="utf-8") as f:
        action_description_list = [
            re.sub(r"Step\d+:", "", line).strip().replace('"', "'")
            for line in f.readlines() if line.strip()
        ]

    token_usage = 0
    prompt_tokens = 0
    completion_tokens = 0
    evidence_steps = []
    confidence_by_step = {}

    start_time = time.perf_counter()
    for step in range(1, step_count + 1):
        action_description = action_description_list[step - 1]
        anno_image = os.path.join(anno_image_path, app_name, str(testid), f'{step}-processed.jpg')
        image1 = os.path.join(images_path, app_name, str(testid), f'{step}.jpg')
        image1_after = os.path.join(images_path, app_name, str(testid), f'{step + 1}.jpg')

        if compare_images(image1, image1_after):
            evidence_steps.append(build_non_response_step(step))
            confidence_by_step[step] = 1.0
            continue

        func_iden_output, usage1, prompt_tokens1, completion_tokens1 = func_iden.func_identification(
            anno_image,
            action_description,
        )
        bug_output, usage2, prompt_tokens2, completion_tokens2 = response_ver.response_verification(
            image1_after,
            func_iden_output,
        )
        parsed_output = parse_detector_output(bug_output)
        evidence_steps.append(
            build_response_step(step, parsed_output, func_iden_output)
        )
        step_confidence = get_float_field(parsed_output, 'confidence')
        if step_confidence is not None:
            confidence_by_step[step] = step_confidence

        token_usage += usage1 + usage2
        prompt_tokens += prompt_tokens1 + prompt_tokens2
        completion_tokens += completion_tokens1 + completion_tokens2

    token_statis.append(token_usage)
    token_in.append(prompt_tokens)
    token_out.append(completion_tokens)

    bug_record = build_bug_record(evidence_steps, confidence_by_step)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(bug_record, f, ensure_ascii=False, indent=4)

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
            future.result()
        except Exception as e:
            print(f"task {futures[future]} failed: {e}")

with open(os.path.join(base_dir, 'token_usage.txt'), 'a') as f:
    for num in token_statis:
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
