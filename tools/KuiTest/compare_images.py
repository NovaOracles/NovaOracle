from PIL import Image

def compare_images(image_path1: str, image_path2: str) -> bool:
    img1 = Image.open(image_path1)
    img2 = Image.open(image_path2)
    if img1.size != img2.size or img1.mode != img2.mode:
        return False
    if img1.tobytes() == img2.tobytes():
        return True
    return False