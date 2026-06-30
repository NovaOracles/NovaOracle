import cv2
def highlight_element_in_screenshot(driver, element, screenshot_path, output_path):
    try:
        location = element.location
        size = element.size
        img = cv2.imread(screenshot_path)
        x1 = int(location['x'])
        y1 = int(location['y'])
        x2 = int(location['x'] + size['width'])
        y2 = int(location['y'] + size['height'])
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 5)
        cv2.imwrite(output_path, img)
        print(f"Annotated elements and saved to: {output_path}")
    except Exception as e:
        print(f"Error finding or annotating element: {e}")