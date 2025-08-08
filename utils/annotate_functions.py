import os
from playwright.async_api import async_playwright
from dotenv import load_dotenv
# from playwright_stealth import stealth_async


load_dotenv()
IMAGE_DIR = os.environ.get('ANNOTATED_SCREENSHOTS_DIR', r'./annotated_screenshots')
ANNOTATION_JS_PATH = 'utils/annotate.js'


def get_unique_filename(directory, base_name):
    """
    Returns a unique file path in the given directory by appending an incrementing suffix.
    E.g., annotated.png, annotated_1.png, ...
    """
    name, ext = os.path.splitext(base_name)
    i = 0
    while True:
        suffix = f"_{i}" if i else ""
        filename = f"{name}{suffix}{ext}"
        full_path = os.path.join(directory, filename)
        if not os.path.exists(full_path):
            return full_path
        i += 1



async def annotate_page(page, image_dir=IMAGE_DIR):
    # Load JS from file
    with open(ANNOTATION_JS_PATH, 'r', encoding='utf-8') as f:
        js_code = f.read()

    os.makedirs(image_dir, exist_ok=True)

    # Generate unique screenshot name
    screenshot_path = get_unique_filename(image_dir, 'annotated.png')

    # Inject JS and capture data
    elements = await page.evaluate(f"""
        () => {{
            {js_code}
            return markPage();
        }}
    """)

    await page.screenshot(path=screenshot_path, full_page=False)
    return screenshot_path, elements