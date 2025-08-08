import asyncio
import os
import time
from typing import List, Tuple

import cv2
import easyocr
from playwright.async_api import async_playwright, Page

async def click_highest_confidence_text(
    page: Page,
    text_to_find_list: List[str],
    ocr_reader: easyocr.Reader,
    save_dir: str = "ocr_debug_output",
    full_page: bool = True
) -> Tuple[bool, Page]:
    print(f"Searching for best match among: {text_to_find_list}")
    os.makedirs(save_dir, exist_ok=True)
    timestamp = int(time.time())
    screenshot_path = os.path.join(save_dir, f"screenshot_{timestamp}.png")

    try:
        await page.screenshot(path=screenshot_path, full_page=full_page)
        print(f"Screenshot saved at '{screenshot_path}'")
    except Exception as e:
        print(f"ERROR taking screenshot: {e}")
        return False, page

    # OCR logic (runs in executor to avoid blocking)
    def ocr_processing_sync():
        if not os.path.exists(screenshot_path) or os.path.getsize(screenshot_path) == 0:
            print("ERROR: Screenshot missing or empty.")
            return None

        results = ocr_reader.readtext(screenshot_path, paragraph=False)

        best_match = None
        best_conf = 0.0
        best_bbox = None
        best_text = ""

        for (bbox, text, prob) in results:
            for target in text_to_find_list:
                if target.lower() in text.lower():
                    if prob > best_conf:
                        best_match = (bbox, text, prob)
                        best_conf = prob
                        best_bbox = bbox
                        best_text = text

        if best_match:
            print(f"Best match: '{best_text}' with confidence {best_conf:.2f}")
            (tl, tr, br, bl) = best_bbox
            center_x = int((tl[0] + br[0]) / 2)
            center_y = int((tl[1] + br[1]) / 2)

            # Annotate image
            img_cv = cv2.imread(screenshot_path)
            cv2.rectangle(img_cv, (int(tl[0]), int(tl[1])), (int(br[0]), int(br[1])), (0, 255, 0), 3)
            cv2.circle(img_cv, (center_x, center_y), 10, (0, 0, 255), -1)
            annotated_path = os.path.join(save_dir, f"annotated_success_{timestamp}.png")
            cv2.imwrite(annotated_path, img_cv)
            print(f"Annotated image saved at '{annotated_path}'")
            return (center_x, center_y)

        print(f"No matches found among: {text_to_find_list}")
        debug_dir = os.path.join(save_dir, "debug_ss")
        os.makedirs(debug_dir, exist_ok=True)
        fail_path = os.path.join(debug_dir, f"debug_not_found_{timestamp}.png")
        os.rename(screenshot_path, fail_path)
        print(f"Saved unannotated image at '{fail_path}'")
        return None

    loop = asyncio.get_running_loop()
    click_coords = await loop.run_in_executor(None, ocr_processing_sync)

    if click_coords:
        await page.mouse.click(click_coords[0], click_coords[1])
        await page.wait_for_load_state('domcontentloaded')
        await asyncio.sleep(3)
        print(f"Click at {click_coords} performed.")
        return True, page
    else:
        print("No valid text found to click.")
        return False, page
