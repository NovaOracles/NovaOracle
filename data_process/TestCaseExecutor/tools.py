import shutil
import pickle
import re
import uiautomator2 as u2
import os
from typing import List
import subprocess
from PIL import Image, ImageDraw, ImageFont

def screenshot(path, name):
    device_name = "emulator-5554"
    device = u2.connect(device_name)
    os.makedirs(path, exist_ok=True)
    device.screenshot(f"{path}/{name}.jpg")

def get_apk_info(apk_path):
    """
    Obtain the package name (package) and the initial Activity (launchable-activity) of the APK
    Dependence: aapt (Android Asset Packaging Tool, located in the build-tools directory of the Android SDK) needs to be installed
    """
    if not os.path.exists(apk_path):
        raise FileNotFoundError(f"APK file does not exist: {apk_path}")

    try:
        # Use the aapt command to parse the APK information
        result = subprocess.run(
            ["aapt", "dump", "badging", apk_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding='utf-8',
            text=True
        )
        output = result.stdout
        if not output:
            raise RuntimeError(f"Failed to parse APK:{result.stderr}")
        # Extract the package name (package: name='com.example.app')
        package_name = None
        for line in output.splitlines():
            if line.startswith("package: name="):
                package_name = line.split("name='")[1].split("'")[0]
                break
        # Extract the initial Activity (launchable-activity: name='com.example.app.MainActivity')
        launch_activity = None
        for line in output.splitlines():
            if line.startswith("launchable-activity: name="):
                launch_activity = line.split("name='")[1].split("'")[0]
                break
        if not package_name or not launch_activity:
            raise RuntimeError("Package name or initial activity not found. Please check if the APK is valid.")
        return package_name, launch_activity
    except FileNotFoundError:
        raise EnvironmentError("The aapt command was not found. Please add the Android SDK's build-tools directory to your environment variables.")
    except Exception as e:
        raise RuntimeError(f"Failed to retrieve APK information:{str(e)}")

def is_app_installed(device_name, package_name):
    """Check whether an application with the specified package name has been installed on the device"""
    try:
        # By specifying the device with "adb -s", query the installed package names
        result = subprocess.run(
            ["adb", "-s", device_name, "shell", "pm", "list", "packages", package_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        # If the output contains "package:<package_name>", then it is installed.
        return f"package:{package_name}" in result.stdout

    except Exception as e:
        print(f"Application installation status check failed: {e}")
        return False

def uninstall_app(device_name: str, package_name: str, timeout: int = 30):
    """Uninstall the application with the specified package name on the device."""
    # Validate input parameters
    if not device_name.strip():
        raise ValueError("Device name (device_name) cannot be empty")
    if not package_name.strip():
        raise ValueError("Package name (package_name) cannot be empty")
    try:
        result = subprocess.run(
            ["adb", "-s", device_name, "uninstall", package_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
    except FileNotFoundError:
        raise RuntimeError("ADB command not found. Ensure ADB is installed and added to system PATH")
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"Uninstallation timed out (Device: {device_name}, Package: {package_name}, Timeout: {timeout}s)")


    message = result.stdout.strip() or result.stderr.strip()
    success = result.returncode == 0
    if not success:
        raise RuntimeError(f"Uninstallation failed: {message} (Device: {device_name}, Package: {package_name})")

def install_apk(device_name: str, apk_path: str, timeout: int = 60, retain_data: bool = True):
    """Install an APK file to a specified Android device via ADB."""
    # Validate input parameters
    if not device_name.strip():
        raise ValueError("Device name cannot be empty")

    if not apk_path or not os.path.exists(apk_path):
        raise ValueError(f"APK file not found: {apk_path}")

    if not apk_path.endswith(".apk"):
        raise ValueError(f"Invalid APK file: {apk_path} (must end with .apk)")

    # Build ADB command
    adb_command = ["adb", "-s", device_name, "install", "-t"]
    if retain_data:
        adb_command.append("-r")  # Add -r flag to retain data if needed
    adb_command.append(apk_path)

    try:
        result = subprocess.run(
            adb_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout = timeout
        )
    except FileNotFoundError:
        raise RuntimeError("ADB command not found. Ensure ADB is installed and in system PATH")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Installation timed out after {timeout}s (Device: {device_name})")

def clear_folder(folder_path):
    """
    Clear all files and subfolders within the specified folder, but keep the folder itself intact.
    Parameter: folder_path: The path of the folder to be emptied
    """
    # Check if the folder exists
    if not os.path.exists(folder_path):
        raise FileNotFoundError(f"The folder does not exist:  {folder_path}")

    # Check if the path is a folder
    if not os.path.isdir(folder_path):
        raise NotADirectoryError(f"Not a folder: {folder_path}")

    # Traverse all the contents within the folder
    for item in os.listdir(folder_path):
        item_path = os.path.join(folder_path, item)
        # If it is a file or symbolic link, simply delete it.
        if os.path.isfile(item_path) or os.path.islink(item_path):
            os.unlink(item_path)
        # If it is a subfolder, recursively delete the entire folder and its contents
        elif os.path.isdir(item_path):
            shutil.rmtree(item_path)

def load_persisted_testcase(PERSIST_PATH):
    if os.path.exists(PERSIST_PATH):
        with open(PERSIST_PATH, 'rb') as f:
            test_case_list = pickle.load(f)
        return test_case_list
    else:
        print("No persisted test case list found!")
        return None

def stitch_images_with_labels(
        image_paths: List[str],
        output_path: str,
        direction: str = 'vertical',
        bg_color: tuple = (255, 255, 255),
        border_width: int = 10,
        border_color: tuple = (200, 200, 200),
        font_scale: float = 0.05,
        text_padding_ratio: float = 0.6
) -> None:

    images = []
    max_width = 0
    max_height = 0

    for img_path in image_paths:
        try:
            img = Image.open(img_path).convert('RGBA')
            images.append(img)
            max_width = max(max_width, img.width)
            max_height = max(max_height, img.height)
        except Exception as e:
            print(f"Warning: Failed to read image {img_path}: {str(e)}")
            continue

    if not images:
        raise RuntimeError("No images were successfully loaded")

    font_size = int(max_width * font_scale)
    font_size = max(24, font_size)

    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except IOError:
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", font_size)
        except IOError:
            font = ImageFont.load_default()

    dummy_draw = ImageDraw.Draw(Image.new('RGB', (1, 1)))
    text_bbox = dummy_draw.textbbox((0, 0), "page_step: 1", font=font)
    text_height = text_bbox[3] - text_bbox[1]

    header_height = int(text_height + (text_height * text_padding_ratio))
    count = len(images)
    if direction == 'vertical':
        total_width = max_width
        total_height = sum(img.height for img in images) + (count * header_height) + ((count - 1) * border_width)
    else:
        total_width = sum(img.width for img in images) + ((count - 1) * border_width)
        total_height = max_height + header_height

    stitched_image = Image.new('RGB', (total_width, total_height), bg_color)
    draw = ImageDraw.Draw(stitched_image)

    current_x = 0
    current_y = 0

    for i, img in enumerate(images):
        label_text = f"page_step: {i + 1}"
        text_bbox = draw.textbbox((0, 0), label_text, font=font)
        text_w = text_bbox[2] - text_bbox[0]
        text_h = text_bbox[3] - text_bbox[1]

        if direction == 'vertical':
            draw.rectangle(
                [(0, current_y), (total_width, current_y + header_height)],
                fill=(245, 245, 245)
            )
            text_pos_y = current_y + (header_height - text_h) // 2 - text_bbox[1]
            text_pos_x = 20
            draw.text((text_pos_x, text_pos_y), label_text, fill=(0, 0, 0), font=font)
            current_y += header_height
            paste_x = (max_width - img.width) // 2
            stitched_image.paste(img, (paste_x, current_y), mask=img if img.mode == 'RGBA' else None)
            current_y += img.height
            if i < count - 1:
                line_y = current_y + border_width // 2
                draw.line([(0, line_y), (total_width, line_y)], fill=border_color, width=3)
                current_y += border_width
        else:
            paste_y = header_height + (max_height - img.height) // 2
            stitched_image.paste(img, (current_x, paste_y), mask=img if img.mode == 'RGBA' else None)
            img_center_x = current_x + img.width // 2
            text_pos_x = img_center_x - text_w // 2
            text_pos_y = (header_height - text_h) // 2 - text_bbox[1]
            draw.text((text_pos_x, text_pos_y), label_text, fill=(0, 0, 0), font=font)
            if i < count - 1:
                line_x = current_x + img.width + border_width // 2
                draw.line([(line_x, 0), (line_x, total_height)], fill=border_color, width=3)
                current_x += img.width + border_width
            else:
                current_x += img.width
    stitched_image.save(output_path, quality=95)

def classify_action(code: str) -> int:
    code = ' '.join(code.split())
    move_count = code.count('move_to_location')
    has_down = 'pointer_down()' in code
    has_release = 'release()' in code
    has_pause = 'pause(' in code
    if move_count >= 2 and has_down and has_release:
        return 1  # Sliding (with at least two occurrences of move_to_location)
    if move_count == 1 and has_down and has_release:
        return 0  # Click (appears only once: move_to_location)
    return 2

def annotate_coordinate_tap(screenshot_path, x, y, output_path):
    img = Image.open(screenshot_path)
    draw = ImageDraw.Draw(img, "RGBA")
    radius = 22
    line_width = 3
    draw.ellipse((x - radius, y - radius, x + radius, y + radius),
                 outline=(255, 0, 0, 220), width=line_width)
    draw.line((x - radius - 20, y, x + radius + 20, y), fill=(255, 0, 0, 255), width=line_width)
    draw.line((x, y - radius - 20, x, y + radius + 20), fill=(255, 0, 0, 255), width=line_width)
    img = img.convert('RGB')
    img.save(output_path)

def annotate_swipe(
        screenshot_path,
        start_x, start_y,
        end_x, end_y,
        output_path
):
    img = Image.open(screenshot_path)
    draw = ImageDraw.Draw(img, "RGBA")

    circle_radius = 34
    line_width = 4
    arrow_head_size = 28

    draw.line(
        [(start_x, start_y), (end_x, end_y)],
        fill=(255, 0, 0, 180),
        width=line_width
    )

    draw.ellipse(
        (start_x - circle_radius, start_y - circle_radius,
         start_x + circle_radius, start_y + circle_radius),
        outline=(0, 180, 0, 220),
        width=4
    )

    draw.ellipse(
        (end_x - circle_radius, end_y - circle_radius,
         end_x + circle_radius, end_y + circle_radius),
        outline=(255, 0, 0, 220),
        width=4
    )

    dx = end_x - start_x
    dy = end_y - start_y
    length = (dx ** 2 + dy ** 2) ** 0.5
    if length > 0:
        ux, uy = dx / length, dy / length
        px, py = -uy, ux

        tip = (end_x, end_y)
        wing1 = (end_x - arrow_head_size * ux + arrow_head_size * 0.4 * px,
                 end_y - arrow_head_size * uy + arrow_head_size * 0.4 * py)
        wing2 = (end_x - arrow_head_size * ux - arrow_head_size * 0.4 * px,
                 end_y - arrow_head_size * uy - arrow_head_size * 0.4 * py)

        draw.polygon([wing1, tip, wing2], fill=(255, 0, 0, 220))

    img = img.convert('RGB')
    img.save(output_path)

def extract_coordinates(code: str) -> list[tuple[float, float]]:
    """
    Extract all the coordinates of "move_to_location(x, y)" from the code string
    Return a list of coordinates in the order of appearance: [(x1, y1), (x2, y2),...]
    """
    pattern = r'move_to_location\s*\(\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*\)'
    matches = re.findall(pattern, code)
    return [(int(x), int(y)) for x, y in matches]