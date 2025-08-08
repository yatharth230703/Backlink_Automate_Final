import os
import asyncio
import json
from playwright.async_api import async_playwright
from agents.backlink_creator_agent import execute_register_loop
from agents.login_agent import execute_login_loop
from agents.login_status_agent import check_login_status_with_ai
from agents.registration_status_agent import check_registration_status_with_ai
from twocaptcha_extension_python import TwoCaptcha


user_data_dir = "./curr-browser-profile"
URL = "https://www.producthunt.com/"

async def main():
    scroll_path = os.path.join("scroll_output_save", "screenshot_full.png")

    # Browser initialization
    extension_path = TwoCaptcha(api_key=os.getenv("TWOCAPTCHA_API_KEY")).load(with_command_line_option=False)
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch_persistent_context(
        user_data_dir=user_data_dir,
        headless=False,
        args=[
            '--disable-extensions-except=' + extension_path,
            '--load-extension=' + extension_path,
            '--start-maximized',
        ],
        viewport=None  # Use full screen size
    )

    page = await browser.new_page()
    await asyncio.sleep(3)
    await page.goto(URL, timeout=300000)
    
    original_text_string = await page.content()

    MAX_ITERS = 20

    # Execute login agent
    page, login_complete = await execute_login_loop(
        page=page,
        browser=browser,
        MAX_ITERS=MAX_ITERS,
        original_text_string=original_text_string,
        scroll_path=scroll_path
    )

    if not login_complete:
        print("⚠️ Login process did not complete successfully, but continuing to registration...")
    else:
        print("✅ Login process completed successfully!")
        # Use AI to verify if we're actually logged in
        print("# =================== Verifying Login Status with AI ===================")
        
        # First check login status on current page without navigation
        print("🔍 Checking login status on current page...")
        is_logged_in = await check_login_status_with_ai(page)
        
        if is_logged_in:
            print("✅ User appears to be logged in on current page")
        else:
            print("⚠️ User doesn't appear logged in on current page, trying homepage...")
            # Wait a bit more for cookies to be saved
            await asyncio.sleep(5)
            # Save current cookies before navigation
            cookies = await page.context.cookies()
            print(f"📁 Saved {len(cookies)} cookies before navigation")
            
            # Navigate to homepage and recheck
            await page.goto(URL, timeout=60000)

            await page.wait_for_load_state('load')
            await asyncio.sleep(3)
            is_logged_in = await check_login_status_with_ai(page)
        
        if not is_logged_in:
            print("# =================== AI Agent Failed to login ===================")
            # TODO: Maintain a counter of how many times the attempt has been taken to log into the page
            raise RuntimeError("AI Agent Failed to login")
            
        else:
            print("✅ AI confirmed user is logged in")

    print("================================== MOVING TO BACKLINK CREATION ==================================")
    
    # Execute backlink creator agent
    page, register_complete = await execute_register_loop(
        page=page,
        browser=browser,
        MAX_ITERS=MAX_ITERS,
        scroll_path=scroll_path
    )

    if register_complete:
        print("🎉 Backlink creation process completed successfully!")
        
        # Wait for backlink creation to be processed and verify completion
        print("# =================== Verifying Backlink Creation Status with AI ===================")
        print("⏳ Waiting for backlink creation to be processed...")
        await asyncio.sleep(10)  # Wait for backlink creation to be processed
        
        # First check backlink creation status on current page
        print("🔍 Checking backlink creation status on current page...")
        is_registration_verified = await check_registration_status_with_ai(page)
        
        if is_registration_verified:
            print("✅ Backlink creation appears to be verified and complete on current page")
        else:
            print("⚠️ Backlink creation doesn't appear complete on current page, trying homepage...")
            # Wait a bit more for any processing
            await asyncio.sleep(5)
            # Save current cookies before navigation
            cookies = await page.context.cookies()
            print(f"📁 Saved {len(cookies)} cookies before navigation")
            
            # Navigate to homepage and recheck
            await page.goto(URL, timeout=60000)
            await page.wait_for_load_state('load')
            await asyncio.sleep(3)
            is_registration_verified = await check_registration_status_with_ai(page)
        
        if not is_registration_verified:
            print("⚠️ AI could not verify backlink creation completion, but backlink creator agent marked it as complete")
            print("🔄 This might indicate the backlink creation is still being processed or requires manual verification")
        else:
            print("✅ AI confirmed backlink creation is complete and verified")
        
        # Additional wait before closing to ensure everything is properly saved
        print("⏳ Waiting additional time for any final processing...")
        await asyncio.sleep(15)
        
    else:
        print("⚠️ Backlink creation process did not complete within maximum iterations")

    print("======================== TASK EXECUTED SUCCESSFULLY ========================")
    await browser.close()
    await playwright.stop()

if __name__ == "__main__":
    asyncio.run(main())
