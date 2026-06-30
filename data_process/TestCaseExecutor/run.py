"""
Execute the test cases, output screenshots and provide descriptions
"""
import os
import configparser
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
from appium_testcase_executor import TestCaseExecutor
import pandas as pd
from tools import get_apk_info, is_app_installed, uninstall_app, install_apk, load_persisted_testcase, classify_action, stitch_images_with_labels, extract_coordinates, annotate_coordinate_tap, annotate_swipe
from page_description_gen import PageDescriptionGen
from action_description_gen import ActionDescriptionGen

config = configparser.ConfigParser()
config.read('config.ini')
device_name = config.get('S', 'device_name')
data_path = config.get('S', 'data_path')

screenshots_path = os.path.join(data_path, 'images', 'screenshots')
annotated_screenshots_path = os.path.join(data_path, 'images', 'annotated_images')
stitch_images_path = os.path.join(data_path, 'images', 'stitch_images')
struct_case_path = os.path.join(data_path, 'struct_case_data')
hierarchy_files_path = os.path.join(data_path, 'hierarchy_files')
page_description_path = os.path.join(data_path, 'page_description_data')
action_description_path = os.path.join(data_path, 'action_description_path')
test_case_path = os.path.join(data_path, 'test_case', 'test_case.csv')

page_description_generator = PageDescriptionGen()
action_description_generator = ActionDescriptionGen()

test_case = pd.read_csv(test_case_path, header=0)

for index, data in test_case.iterrows():
    case = data['TestCase']
    if(pd.isna(case)):
        continue
    test_id = data['ID']
    app_name = data['AppName']
    apk_path = f'{data['ApkPath']}/{data['AppVersion']}.apk'
    app_package, app_activity = get_apk_info(apk_path)

    logging.info("Current test case ID: %s", test_id)
    logging.info("The package name of the app currently being tested: %s", app_package)
    logging.info("Initial activity: %s", app_activity)

    if is_app_installed(device_name, app_package):
       uninstall_app(device_name, app_package)
    install_apk(device_name, apk_path)
    logging.info("Executing test cases on the simulator ...")
    testcase_executor = TestCaseExecutor(device_name, app_package, app_activity, test_id, app_name)
    try:
        testcase_executor.execute_testcase(case)
    except Exception as e:
        logging.error(f"error: {str(e)}")
        raise Exception(f"Error: {str(e)}")
    uninstall_app(device_name, app_package)

    struct_case_file = f'{struct_case_path}/{app_name}/{test_id}.pkl'
    action_description_file = os.path.join(action_description_path, app_name, f"{test_id}.txt")
    page_description_file = os.path.join(page_description_path, app_name, f"{test_id}.txt")
    test_case_list = load_persisted_testcase(struct_case_file)
    step_count = len(test_case_list) #step count

    action_description_text = ""
    page_description_text = ""
    stitch_images_list = []

    # action_description
    for i in range(1, step_count+1):
        action = test_case_list[i - 1]
        action_class = classify_action(action)
        # Annotate special action
        anno_image_before = f'{annotated_screenshots_path}/{app_name}/{test_id}/{i}-processed.jpg'
        if (action_class == 0): # Click on the coordinates
            anno_image = f'{annotated_screenshots_path}/{app_name}/{test_id}/{i}-processed-co.jpg'
            if os.path.exists(anno_image) == False:
                coordinate = extract_coordinates(action)[0]
                annotate_coordinate_tap(anno_image_before, coordinate[0], coordinate[1], anno_image)
        elif (action_class == 1): # swip
            anno_image = f'{annotated_screenshots_path}/{app_name}/{test_id}/{i}-processed-sw.jpg'
            if os.path.exists(anno_image) == False:
                coordinate_pre = extract_coordinates(action)[0]
                coordinate_post = extract_coordinates(action)[1]
                annotate_swipe(anno_image_before, coordinate_pre[0], coordinate_pre[1], coordinate_post[0], coordinate_post[1], anno_image)
        else:
            anno_image = anno_image_before

        action_description, t1, t2, t3 = action_description_generator.get_output(anno_image, action)
        action_description_text = action_description_text + f'Step{i}:' + action_description + "\n"

    action_description_file_folder = os.path.dirname(action_description_file)
    os.makedirs(action_description_file_folder, exist_ok = True)
    with open(action_description_file, "w", encoding="utf-8") as f2:
        f2.write(action_description_text)

    # page_description
    for i in range(1, step_count + 2):
        image = f'{screenshots_path}/{app_name}/{test_id}/{i}.jpg'
        page_description, t1, t2, t3 = page_description_generator.get_output(image)
        page_description_text = page_description_text + page_description + "\n"

    page_description_file_folder = os.path.dirname(page_description_file)
    os.makedirs(page_description_file_folder, exist_ok=True)
    with open(page_description_file, "w", encoding="utf-8") as f2:
        f2.write(page_description_text)

    # Output file of stitched screenshots
    for i in range(1, step_count + 1):
        anno_image = f'{annotated_screenshots_path}/{app_name}/{test_id}/{i}-processed.jpg'
        stitch_images_list.append(anno_image)
    last_image = f'{screenshots_path}/{app_name}/{test_id}/{step_count + 1}.jpg'
    stitch_images_list.append(last_image)

    stitch_image_output_dir = f'{stitch_images_path}/{app_name}'
    os.makedirs(stitch_image_output_dir, exist_ok=True)
    stitch_image_output_path = os.path.join(stitch_image_output_dir, f'{test_id}.jpg')
    stitch_images_with_labels(
        image_paths=stitch_images_list,
        output_path=stitch_image_output_path,
        direction='horizontal'
    )
    print("stitch image saved")