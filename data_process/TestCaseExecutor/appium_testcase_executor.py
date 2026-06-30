import configparser
import time
import pickle
import re
import shutil
import os
from appium import webdriver
from appium.options.android import UiAutomator2Options
from element_location import highlight_element_in_screenshot
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.actions import interaction
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.common.actions.pointer_input import PointerInput

config = configparser.ConfigParser()
config.read('config.ini')
device_name = config.get('S', 'device_name')
data_path = config.get('S', 'data_path')

screenshots_path = os.path.join(data_path, 'images', 'screenshots')
annotated_screenshots_path = os.path.join(data_path, 'images', 'annotated_images')
struct_case_path = os.path.join(data_path, 'struct_case_data')
hierarchy_files_path = os.path.join(data_path, 'hierarchy_files')


class TestCaseExecutor:
    def __init__(self, device_name, app_package, app_activity, test_id, app_name):
        if not all([device_name, app_package, app_activity]):
            raise ValueError("Error ! device_name, app_package, and app_activity cannot be empty!")
        self.test_id = test_id
        self.device_name = device_name
        self.app_package = app_package
        self.app_activity = app_activity
        self.app_name = app_name
        self.desired_caps = {
            "platformName": "Android",
            "appium:automationName": "UiAutomator2",
            "appium:deviceName": self.device_name,
            "appium:appPackage": self.app_package,
            "appium:appActivity": self.app_activity,
            #"noReset": True
        }
        self.PERSIST_PATH = f'{struct_case_path}/{app_name}/{test_id}.pkl'

    def execute_testcase(self, test_case):

        pattern_sendkey = r'^el\w+\.send_keys\(".*"\)$'
        test_case_list = self.__split_code(test_case)
        driver = None

        screenshot_dir = f'{screenshots_path}/{self.app_name}/{self.test_id}'
        annotated_dir = f'{annotated_screenshots_path}/{self.app_name}/{self.test_id}'
        hierarchy_dir = f'{hierarchy_files_path}/{self.app_name}/{self.test_id}'
        os.makedirs(screenshot_dir, exist_ok=True)
        os.makedirs(annotated_dir, exist_ok=True)
        os.makedirs(hierarchy_dir, exist_ok=True)

        try:
            appium_options = UiAutomator2Options().load_capabilities(self.desired_caps)
            driver = webdriver.Remote('http://localhost:4723', options=appium_options)
            driver.implicitly_wait(10)
            case_locals = {'driver': driver}
            time.sleep(5)

            for step, case in enumerate(test_case_list, 1):
                print("step: ", step, "/", len(test_case_list))
                path1 = f'{screenshot_dir}/{step}.jpg' #screenshot before operation
                path2 = f'{annotated_dir}/{step}-processed.jpg'
                path_heri = f'{hierarchy_dir}/{step-1}.xml'
                driver.save_screenshot(path1)
                if step == 1 :
                    ui_hierarchy = driver.page_source
                    with open(path_heri, "w", encoding="utf-8") as f:
                        f.write(ui_hierarchy)

                if case.startswith('actions') or case.startswith('driver'):
                    driver.save_screenshot(path2)
                    exec(case)
                elif case.startswith('el'):
                    pre_ope, ope, last_line = self.__split_last_operation(case)
                    exec(pre_ope, globals(), case_locals)
                    ele = case_locals[list(case_locals.keys())[-1]]
                    text_pre = ""
                    if(re.match(pattern_sendkey, last_line)):
                        text_pre = ele.text
                    highlight_element_in_screenshot(driver, ele, path1, path2)
                    exec(ope, globals(), case_locals)
                    if (re.match(pattern_sendkey, last_line)):
                        text_end = ele.text
                        text = f'# pre-text:\"{text_pre}\", post-text:\"{text_end}\"'
                        test_case_list[step - 1] += text + '\n'
                time.sleep(5)
                if (step == len(test_case_list)):
                    path = f'{screenshot_dir}/{step + 1}.jpg'
                    driver.save_screenshot(path)


                ui_hierarchy = driver.page_source
                with open(path_heri, "w", encoding="utf-8") as f:
                    f.write(ui_hierarchy)

            print("Test execution successful")
            os.makedirs(os.path.dirname(self.PERSIST_PATH), exist_ok=True)
            with open(self.PERSIST_PATH, 'wb') as f:
                pickle.dump(test_case_list, f)
            print(f"Test case list saved to: {self.PERSIST_PATH}")

        except Exception as e:
            print(f"Fail: {e}")
            if os.path.exists(screenshot_dir):
                shutil.rmtree(screenshot_dir)
            if os.path.exists(annotated_dir):
                shutil.rmtree(annotated_dir)
            if os.path.exists(hierarchy_dir):
                shutil.rmtree(hierarchy_dir)

        finally:
            if driver is not None:
                driver.quit()

        return

    def __split_code(self, case):
        """
        Break the entire test case into individual operations.
        """
        pattern_el = r'^(\w+)\s*='
        pattern_dot = r'^(\w+)\.'

        case_list1 = [block.strip() for block in case.split('\n\n') if block.strip()]
        case_list2 = []
        for block in case_list1:
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            i = 0
            while i < len(lines):
                if lines[i].startswith('el'):
                    element_case = ''
                    el = re.match(pattern_el, lines[i]).group(1)
                    element_case += lines[i] + '\n'
                    i += 1
                    while i < len(lines) and re.match(pattern_dot, lines[i]) and re.match(pattern_dot, lines[i]).group(1) == el:
                        element_case += lines[i] + '\n'
                        i += 1
                    case_list2.append(element_case)

                elif lines[i].startswith('driver'):
                    case_list2.append(lines[i])
                    i += 1
                elif lines[i].startswith('actions'):
                    actions_case = ''
                    while i < len(lines) and lines[i].startswith('actions'):
                        actions_case = actions_case + lines[i] + '\n'
                        i += 1
                    case_list2.append(actions_case)

        return case_list2

    def __split_code_old(self, case):
        """
        Break the entire test case into individual operations.
        """
        case_list1 = [block.strip() for block in case.split('\n\n') if block.strip()]
        case_list2 = []
        for block in case_list1:
            if block.startswith('a'):
                case_list2.append(block)
            elif block.startswith('e'):
                opes = block.splitlines()
                case_list2.extend([f"{opes[i]}\n{opes[i + 1]}" for i in range(0, len(opes), 2)])
        return case_list2

    def __split_last_operation(self, operation):
        """Delete and return the last line of the string."""
        lines = operation.splitlines()
        pre_ope = lines[0]
        last_line = lines[-1]
        last_ope = '\n'.join(lines[1:])
        return pre_ope, last_ope, last_line