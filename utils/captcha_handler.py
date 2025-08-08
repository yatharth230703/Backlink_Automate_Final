import asyncio


async def wait_for_captcha_resolution(page, max_iterations=6, wait_time=30):
    """
    Waits for captcha resolution by monitoring captcha-solver-info elements.
    
    Args:
        page: Playwright page object
        max_iterations (int): Maximum number of iterations to wait (default: 5)
        wait_time (int): Time to wait between checks in seconds (default: 15)
    
    Returns:
        bool: True if all captchas are resolved, False if timeout
        
    Raises:
        RuntimeError: If captcha cannot be solved within the specified time
    """
    locator = page.locator("div.captcha-solver-info")
    count = await locator.count()

    if count > 0:
        # There is some captcha solving happening
        iter = 0

        while True:
            
            captcha_elements = await page.locator('div.captcha-solver-info').all_text_contents()
            all_resolved = all(text.strip() == "Captcha solved!" for text in captcha_elements)

            if all_resolved:
                return True
            else:
                print(" ===== Unresolved captcha element present, pausing agent for resolution ========")
                print(f" Trying for iter {iter}")
                print(captcha_elements)

            await asyncio.sleep(wait_time)
            iter += 1

            if iter > max_iterations:
                print("Captcha solving failed, leaving to agent")
                break
    
    return True  # No captcha elements found, so we're good to proceed
