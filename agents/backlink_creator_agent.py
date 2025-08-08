from agents.base_agent import BaseAgent
import easyocr
import torch
import asyncio
import os
from utils.captcha_handler import wait_for_captcha_resolution
from utils.playwright_functions import cross_reference, click, fill_fields
from utils.annotate_functions import annotate_page
from utils.close_popup import click_highest_confidence_text
from agents.verification_agent import vericomm_agent 

class BacklinkCreatorAgent(BaseAgent):
    """Backlink creator agent for handling business listing and press release creation processes."""
    
    def get_tool_schema(self) -> list:
        """Return the tool schema for backlink creator agent."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "submit_directory_action",
                    "description": "Decide which interactive elements to click or fill to progress the backlink creation flow on a directory page.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "popup": {
                                "type": "boolean",
                                "description": "ANYTHING RELATED TO ACCEPTING COOKIES ON ANY PART OF THE WEBPAGE . Simply scan the image for any popups/ elements that are overlaying on the main screen or appear on the screen top/right/bottom/left. Usually these can be popups for accepting cookies where the user needs to mention whether they accept cookies or not , which is usually to accept cookies. Return true if popup detected ,false if not detected."
                            },
                            "click": {
                                "type": "integer",
                                "description": "The ID of the element to be clicked (e.g. login/signup/next). Only one at a time. Return -1 if nothing to click."
                            },
                            "write": {
                                "type": "array",
                                "description": "List of [elementId, value] pairs. Each pair is an array of exactly two strings: the ID of the element and the text to enter.",
                                "items": {
                                    "type": "array",
                                    "items": {
                                        "type": "string",
                                        "description": "Either the element ID (first position) or the input text (second position)."
                                    },
                                    "minItems": 2,
                                    "maxItems": 2
                                }
                            },
                            "order": {
                                "type": "integer",
                                "enum": [1, 2, 3, 4],
                                "description": "1: click then input, 2: input then click, 3: only click, 4: only input"
                            },
                            "action_taken": {
                                "type": "string",
                                "description": "Describe in detail what action was taken by the agent"
                            },

                            "process_status": {
                                "type": "boolean",
                                "description": "True ONLY if on the current page image you can see visual confirmation that BUSINESS LISTING or PRESS RELEASE creation has been SUCCESSFULLY completed (success messages about business listing creation, press release submission confirmation, confirmation pages showing business is registered on directory, business profile created, press release published, etc.). False if you just completed user login/signup, clicked a submit button without seeing results, or see general login success messages like 'Erfolgreich registriert!'. Do NOT set to True for user account creation or general welcome messages - only for actual business listing or press release completion."
                            },
                            "captcha_detected": {
                                "type": "boolean",
                                "description": "Set to true ONLY if you can clearly see a captcha challenge on the screen (reCAPTCHA, hCaptcha, image verification, puzzle solving, etc.). The captcha solving system will then be activated to handle it automatically. DO NOT set to true unless you can visually confirm a captcha is present on the page."
                            },
                            "scroll_needed": {
                                "type": "boolean",
                                "description": "Set to true ONLY if all visible form elements are completely filled/selected and all required checkboxes are checked, but essential buttons (Submit/Continue/Next/Send/Senden/Weiter) are missing from the current viewport. DO NOT scroll if there are any unfilled fields, empty dropdowns, or unchecked required checkboxes visible."
                            },
                            "scroll_direction": {
                                "type": "string",
                                "enum": ["none", "up", "down"],
                                "description": "Direction to scroll when scroll_needed is true. Use 'down' to find submit buttons typically at bottom of forms, 'up' for navigation elements at top, 'none' when no scrolling needed."
                            },
                            "scroll_reason": {
                                "type": "string",
                                "description": "Brief explanation for why scrolling is needed or why it's not needed. Examples: 'All fields filled but submit button not visible' or 'Form fields still need completion' or 'No scrolling needed, taking action'"
                            }
                        },
                        "required": ["popup", "click", "write", "order", "action_taken", "process_status", "scroll_needed", "scroll_direction", "scroll_reason"]
                    }
                }
            }
        ]
    
    def get_agent_prompt(self) -> str:
        """Return the system prompt for backlink creator agent."""
        return f"""
    You are a world-class AI automation engine and are adept at creating backlinks by registering businesses into websites and directories. You are based in Germany and fluent in German. The directories you will register our business into would primarily be in German.

    ## Main goal
    You are called ONLY AFTER the user login process has been completed successfully. Your SOLE MISSION is:
    
    **CREATE AND SUBMIT A BUSINESS LISTING OR PRESS RELEASE FOR BACKLINK CREATION** - Find and complete the business listing/press release creation process on the directory platform to create valuable backlinks for SEO purposes.
    
    # Analyze the given image and the given list of interactive elements that you can see on the image. You need to determine which of these are responsible for creating a business listing or press release on the directory webpage. It is important that you pay attention to the image for getting the appropriate context and the interactive elements list for which values to click. 
    
    The ULTIMATE GOAL is to create a business listing or press release on the directory using the business data provided to generate high-quality backlinks for SEO. The user is already logged in, so focus entirely on finding and completing the business listing/press release creation process.
    
    **IMPORTANT**: Look specifically for options like:
    - "Pressemitteilung versenden" (Send Press Release)
    - "Pressemitteilung erstellen" (Create Press Release) 
    - "Neue Pressemitteilung" (New Press Release)
    - "Unternehmen hinzufügen" (Add Company)
    - "Eintrag erstellen" (Create Entry)
    - "Business listing" creation options
    
    **DO NOT** consider general success messages like "Erfolgreich registriert!" as completion unless they specifically mention business listing or press release creation completion.
    
    You are also given a list of interactible elements {{list}}.
    You need to perform click or fill actions - click in case of button-like interactible elements (remember they are in German), and fill in case of form-like interactible elements. You are also given a thorough history through a list of commands that tell you about: (a) the actions that you took, (b) if those actions passed or failed, (c) suggestion provided by the expert on what to do next. You need to treat this historical record as a reference and allow it to guide you in order to determine what to do next.
    
        
    BUSINESS_DATA = {self.get_business_data_json()}
    Assume/deduce all remaining information that might be required.

    ## Step-by-step plan
    1. **Historical Analysis**
        Take into account the historical records that are given to you, learn from your mistakes and implement the suggestions given to you ALONG WITH your own reasoning so as to move forward with the most logically sound step, and create a solid action plan regarding what to do right now.
    2. **Image Analysis**  
        Take a deep look at the image. Remember to detect any and all popups; if it is, return true. A popup is a rare occurrence, but it can happen. The image of the automation process usually should contain the image of a webpage and the annotated, numbered bounding boxes of the interactible elements.
        You need to determine based on the history given to you and the main goal of the task, what action you should take now, and by action I mean which of the interactible elements
        you should interact with (i.e. click a button/fill in some value)
    3. **Things to keep in mind**
        You need to keep in mind that this entire procedure is for creating backlinks by registering my business onto said directory, so you should effectively utilize information I provided as BUSINESS_DATA to properly fill in information.
        The user is already logged in, so your focus should be entirely on finding and completing the business listing creation process. You will have all the information you need in the BUSINESS_DATA file; navigating through filling out the information should not be tough. Leave optional fields blank and assume any missing data.
        Simply add your output to the appropriate json format as suggested above.
    4. **Implementing Action**
        When you have decided what you need to do, simply do that by sharing which element of all numbered ones to interact with, and keep in mind that sometimes, we need to click a button before entering text,
        or enter some text and THEN click a button. These minute things matter, so it'll be good if you share the order as well. Look for elements responsible for business listing creation/submission/registration - these should be obvious once you identify them.
    5. **Indications for process completion**
        IMPORTANT: Only mark process_status as true when you can clearly see visual confirmation that the BUSINESS LISTING or PRESS RELEASE creation process has been SUCCESSFULLY COMPLETED on the current page. This includes:
        - Success messages specifically about business listing creation like "Business listing created", "Business registered successfully", "Listing published", "Business profile created"
        - Success messages about press release creation like "Pressemitteilung erfolgreich versendet", "Press release published", "Mitteilung wurde übermittelt"
        - Confirmation pages showing the business listing or press release has been submitted/published
        - Business profile/listing pages that show the business details are now live on the directory
        - Messages indicating the business listing or press release is pending approval or has been approved
        
        DO NOT mark process_status as true for:
        - Simply clicking a "Submit" or "Send" button without seeing the result
        - General "Welcome" messages or login confirmations like "Erfolgreich registriert!" that don't specifically mention business listing/press release creation
        - Dashboard or navigation pages without business listing/press release creation confirmation
        - User account creation or login success messages
        
        The process is only complete when the BUSINESS LISTING or PRESS RELEASE itself has been created and submitted on the directory.
    6.  **Finding business listing creation options**
        Since the user is already logged in, look for options to create a business listing or press release such as:
        - "Pressemitteilung versenden" (Send Press Release) - PRIORITY TARGET
        - "Pressemitteilung erstellen" (Create Press Release) - PRIORITY TARGET  
        - "Neue Pressemitteilung" (New Press Release) - PRIORITY TARGET
        - "Add Business" / "Unternehmen hinzufügen"
        - "Create Listing" / "Eintrag erstellen" 
        - "Register Business" / "Geschäft registrieren"
        - "Submit Business" / "Unternehmen einreichen"
        - "Add Company" / "Firma hinzufügen"
        - "List Your Business" / "Ihr Unternehmen listen"
        - "Create Profile" / "Profil erstellen"
        - Plus signs (+) or "Add" buttons in business/listing sections
        - Navigation menu items related to business listings or press releases
        
        **CRITICAL**: If you see "Pressemitteilung versenden" or similar press release options, prioritize those as they are the primary way to create business listings on this platform.
    7. **CAPTCHA DETECTION**
        If you can clearly see a captcha challenge on the page (reCAPTCHA, hCaptcha, image verification puzzles, "I'm not a robot" checkboxes, etc.), set captcha_detected to true. The automated captcha solving system will then be activated to handle it. Only set this when you can visually confirm a captcha is present - do not assume based on loading states or other factors.
    8. **Smart Scrolling Control**
        You now have the ability to control page scrolling when needed:
        
        **CRITICAL SCROLLING PRIORITY RULES:**
        
        **PRIORITY 1 - DO NOT SCROLL IF VISIBLE ELEMENTS NEED COMPLETION:**
        **NEVER scroll if the current viewport contains any:**
        - Empty/unfilled form fields (text boxes, dropdowns, etc.)
        - Unchecked required checkboxes or radio buttons
        - Unselected dropdown menus
        - Any other interactive elements that still need user input
        
        **PRIORITY 2 - SCROLL ONLY WHEN ALL VISIBLE ELEMENTS ARE COMPLETE:**
        **A. Form Completion Without Submit Option:** If ALL visible form fields are FILLED/COMPLETED and ALL checkboxes are properly checked, but no submit/continue/send button is visible in the current viewport, set scroll_needed to true to find the submission mechanism.
        
        **B. Repeated Failed Actions:** If the same action is being attempted multiple times with no visible change, ALL visible elements are complete, and the target element (button/link) is not visible in the current view, set scroll_needed to true to locate the correct interactive element.
        
        **Direction Logic:**
        - Use 'down' if looking for submit buttons, continue buttons, send buttons, or elements typically at the bottom of forms
        - Use 'up' if looking for navigation elements, headers, error messages or elements typically at the top
        - Use 'none' when no scrolling is needed
        
        **Setting scroll_needed and scroll_direction:**
        - Only set scroll_needed to true when ALL visible form elements are completely filled and essential buttons are missing
        - Provide a clear scroll_reason explaining your decision
        - The scrolling will be executed automatically based on your decision
    ## Guidelines
    * Always enter the correct details that you have to write about the elements that should be interacted with  
    * Always respect the history and the main task at hand, and make decisions according to what is required and what has been accomplished to-date, along with what needs to be accomplished  
    * After making all the decisions regarding which step to take, write down the overall action that you took and return under action_taken. Return completed if goal is achieved.
    * CRITICAL: Only set process_status to true when you can visually confirm successful BUSINESS LISTING or PRESS RELEASE completion on the current page, NOT immediately after clicking submit/send buttons
    * CRITICAL: Do NOT mark process_status as true for general messages like "Erfolgreich registriert!" unless they specifically mention business listing or press release creation
    * REMEMBER: The user is already logged in - your job is to create the business listing or press release
    * Look for business listing creation options like "Add Business", "Create Listing", "Register Business", etc.
    * PRIORITY: Look for press release options like "Pressemitteilung versenden", "Pressemitteilung erstellen", "Neue Pressemitteilung" 
    * If ever encountered with numerous possible options for proceeding with business listing creation, always choose the free tier option/free plan 
    * Always use the history as reference 
    * If the buttons themselves don't have any text on them try to click the ones that are nearby the relevant text
    * Do not repeat an action for more than 3 times in a row. Invent new strategies to move forward if you see the same action repeated in the history.
    * Keep an eye out for any elements that carry the filled tag; if it is true then don't bother filling that particular element, it means it is preselected
    * If you encounter a place to insert text where you don't know what to write / not given in business data then just make a guess
    * PLEASE MAKE SURE TO CHECK ALL ACKNOWLEDGEMENT BOXES / I AGREE BOXES / I CONSENT BOXES and other similar check-boxes.
    * **SCROLLING DECISION GUIDELINES**: Only set scroll_needed to true when ALL visible elements are completely filled/completed and essential buttons (Submit/Continue/Next/Send/Senden/Weiter) are missing from current view. Do NOT scroll if any visible form fields, dropdowns, or checkboxes still need completion. Always provide a clear scroll_reason for your decision.
    * **FORM COMPLETION PRIORITY**: Always complete ALL visible form elements before considering scrolling. This includes text inputs, dropdowns, checkboxes, radio buttons, and any other interactive elements that require user input.

    ## Strict JSON output wrapper
    You are to strictly follow the given json output format. Your output should contain nothing but the json formatted output, no headers no headings no footers and definitely no ```json``` tags. Pure, simple json starting and ending with curly brace.
    {{
        popup: (If a popup is detected or not) |bool|
        click: (ID of element that needs to be clicked, one click at a time) |int|  , 
        write : [
                [ID of element that needs to accept input, value to be written in field] |list|,
                [ID of element that needs to accept input, value to be written in field] |list|, 
                [ID of element that needs to accept input, value to be written in field] |list|
                ] |list|,
        order : (1 if first click then input, 2 if first input then click, 3 if only click, 4 if only input) |int| ,
        action taken : what action was taken |str| ,
        process_status : (True ONLY if you can see visual confirmation of successful BUSINESS LISTING or PRESS RELEASE creation completion on current page, False otherwise - do NOT set to True immediately after clicking submit buttons or for general login success messages like "Erfolgreich registriert!") |bool|,
        captcha_detected : True/False (ONLY set to true when you can clearly see a captcha challenge on screen like reCAPTCHA, hCaptcha, image verification, etc.) |bool|,
        scroll_needed : True/False (ONLY set to true when all visible elements are filled but essential buttons are missing from viewport) |bool|,
        scroll_direction : "none"/"up"/"down" (direction to scroll when scroll_needed is true) |str|,
        scroll_reason : "explanation for scrolling decision" |str|
    }}
    """


# Create instance and function for backward compatibility
backlink_creator_agent_instance = BacklinkCreatorAgent()

def register_agent(image_path: str, user_prompt: str, message_history: list, debug: bool = False):
    """
    Backward compatible function for backlink creator agent.
    
    Args:
        image_path: Path to screenshot image
        user_prompt: User prompt with elements data
        message_history: Previous conversation history
        debug: Whether to print debug information
        
    Returns:
        Tuple of (data_uri, agent_result)
    """
    return backlink_creator_agent_instance.execute(image_path, user_prompt, message_history, debug)


async def execute_register_loop(page, browser, MAX_ITERS, scroll_path):
    """
    Execute the backlink creator agent loop.
    
    Returns:
        Tuple of (page, register_complete)
    """
    i = 0
    history_list = []
    message_history = []
    scroll = 0
    
    print("================================== START BACKLINK CREATOR AGENT ==================================")
    
    while i < MAX_ITERS:

        agent_inputs = [{"history": history_list}]
        
        # Initialize scrolling control variable for this iteration
        backlink_agent_handled_scroll = False
        
        # Handle closed pages
        if page.is_closed():
            pages = page.context.pages
            if not pages:
                raise RuntimeError("All tabs closed—nothing left to do.")
            page = pages[-1]
            print(f"[DEBUG] page was closed; switched to {page.url}")
        
        await page.wait_for_load_state('load')
        img_path, elements = await annotate_page(page)
        
        if len(history_list) > 0:
            elements.extend(agent_inputs)
        elements_str = str(elements)

        cleaned_elements = [{'elements': [{'id': elem['id'], 'tag': elem['tag'], 
                                         'text': elem.get('text', '')[:200] if len(elem.get('text', '')) > 200 else elem.get('text', ''), 
                                         'labelText': elem.get('labelText', '')[:200] if len(elem.get('labelText', '')) > 200 else elem.get('labelText', '')} 
                                        for elem in elements if 'id' in elem]}]
        cleaned_elements_str = str(cleaned_elements)


        
        # Call the backlink creator agent
        prev_img_uri, agent_result = register_agent(img_path, cleaned_elements_str, message_history, True)
        agent_result_str = str(agent_result)
        
        # Prepare message history
        temp_message = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": cleaned_elements_str},
                    {"type": "image_url", "image_url": {"url": prev_img_uri}}
                ]
            },
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": agent_result_str}
                ]
            }
        ]
        
        elements_only = [e for e in elements if 'id' in e]
        
        # Handle popup detection
        if agent_result.get("popup"):
            success, page = await click_highest_confidence_text(
                page=page,
                text_to_find_list=["Alle Akzeptieren", "Akzeptieren", "Accept", "zustimmen"],
                ocr_reader=easyocr.Reader(['de', 'en'], gpu=torch.cuda.is_available()),
                save_dir=os.getcwd()
            )
            if success:
                continue
            else:
                print("minor popup, can be ignored")
        
        # Handle captcha detection and resolution
        if agent_result.get("captcha_detected"):
            print("🔐 Captcha detected by agent - starting captcha resolution process...")
            try:
                captcha_resolved = await wait_for_captcha_resolution(page)
                if captcha_resolved:
                    print("✅ Captcha resolution completed successfully")
                    history_list.append({
                        "action_taken": "captcha_detected_and_resolved",
                        "status": "success",
                        "note": "Agent detected captcha and automatic resolution was successful"
                    })
                else:
                    print("⚠️ Captcha resolution timed out or failed")
                    history_list.append({
                        "action_taken": "captcha_detected_but_failed",
                        "status": "failed", 
                        "note": "Agent detected captcha but automatic resolution failed"
                    })
                # Continue to next iteration after captcha handling
                i += 1
                continue
            except Exception as e:
                print(f"❌ Error during captcha resolution: {e}")
                history_list.append({
                    "action_taken": "captcha_resolution_error",
                    "status": "failed",
                    "error": str(e)
                })
                # Continue anyway in case captcha was actually resolved
        
        elements_click, elements_input = cross_reference(elements_only, agent_result)
        
        # Execute actions based on order
        match agent_result['order']:
            case 1:
                print("Executing click and fill (order 1)")
                page = await click(elements_click, page)
                await page.wait_for_load_state('load')
                page = await fill_fields(elements_input, page)
                await page.wait_for_load_state('load')
            case 2:
                print("Executing fill and click (order 2)")
                page = await fill_fields(elements_input, page)
                await page.wait_for_load_state('load')
                page = await click(elements_click, page)
                await page.wait_for_load_state('load')
            case 3:
                print("Executing click (order 3)")
                page = await click(elements_click, page)
                await page.wait_for_load_state('load')
            case 4:
                print("Executing fill (order 4)")
                page = await fill_fields(elements_input, page)
                await page.wait_for_load_state('load')
        
        # Handle backlink creator agent scrolling decisions
        if agent_result.get("scroll_needed") and agent_result.get("scroll_direction") != "none":
            scroll_direction = agent_result.get("scroll_direction", "none")
            scroll_reason = agent_result.get("scroll_reason", "No reason provided")
            
            print(f"📜 Backlink Creator Agent Scrolling: {scroll_direction} - Reason: {scroll_reason}")
            
            if scroll_direction == "up":
                await page.evaluate("window.scrollBy(0, -200)")
                print("⬆️ Scrolled up by 200px per backlink creator agent decision")
            elif scroll_direction == "down":
                await page.evaluate("window.scrollBy(0, 200)")
                print("⬇️ Scrolled down by 200px per backlink creator agent decision")
            
            # Add scroll action to history
            history_list.append({
                "action_taken": f"backlink_agent_scroll_{scroll_direction}",
                "status": "executed",
                "reason": scroll_reason,
                "scroll_direction": scroll_direction
            })
            
            # Wait for scroll to complete and page to stabilize
            await asyncio.sleep(1)
            await page.wait_for_load_state('load')
            
            # Skip verification agent for this iteration since backlink agent handled scrolling
            backlink_agent_handled_scroll = True
        
        # Handle potential page closure or navigation after actions
        if page.is_closed():
            pages = page.context.pages
            if not pages:
                raise RuntimeError("All tabs closed after action execution.")
            page = pages[-1]
            print(f"[DEBUG] Page was closed after action; switched to {page.url}")
        
        # Wait for any potential navigation/redirect to complete
        try:
            await page.wait_for_load_state('networkidle', timeout=5000)
        except Exception as e:
            print(f"[DEBUG] Network idle timeout or error: {e}")
            # Continue anyway as the page might still be usable
        
        # Additional wait to ensure page is stable
        await asyncio.sleep(2)
        
        # Verification and history update
        try:
            img_path_new, _ = await annotate_page(page)
        except Exception as e:
            print(f"[DEBUG] Error in annotate_page after action: {e}")
            # If page context is destroyed, wait and try again
            if "Execution context was destroyed" in str(e) or "Page.evaluate" in str(e):
                print("[DEBUG] Page context destroyed, waiting for page to stabilize...")
                await asyncio.sleep(3)
                
                # Check if page is still valid
                if page.is_closed():
                    pages = page.context.pages
                    if not pages:
                        raise RuntimeError("All tabs closed after navigation.")
                    page = pages[-1]
                    print(f"[DEBUG] Switched to new page: {page.url}")
                
                try:
                    await page.wait_for_load_state('load', timeout=10000)
                    img_path_new, _ = await annotate_page(page)
                except Exception as retry_error:
                    print(f"[DEBUG] Retry failed: {retry_error}")
                    # Use the previous image path as fallback
                    img_path_new = img_path
            else:
                # For other errors, re-raise
                raise e
        current_scroll_path = scroll_path.replace("screenshot_0.png", f"screenshot_{scroll}.png")
        try:
            await page.screenshot(path=current_scroll_path, full_page=True)
        except Exception as e:
            print(f"[DEBUG] Error taking screenshot: {e}")
            # If screenshot fails due to navigation, try again after wait
            if "Target page" in str(e) or "Page.screenshot" in str(e):
                await asyncio.sleep(2)
                try:
                    await page.screenshot(path=current_scroll_path, full_page=True)
                except Exception:
                    print(f"[DEBUG] Screenshot retry failed, skipping screenshot for iteration {i}")
        scroll += 1
        
        # Skip vericomm automatic scrolling if backlink agent handled scrolling
        if not backlink_agent_handled_scroll:
            vericomm_output = vericomm_agent(img_path, img_path_new, current_scroll_path, 
                                                history_list, current_action=agent_result["action_taken"])
            print("======================== VERICOMM OUTPUT (start) ========================")
            print(vericomm_output)
            print("======================== VERICOMM OUTPUT (end) ========================")
            
            if vericomm_output["scroll_up_down"] == 1:
                await page.evaluate("window.scrollBy(0, -200)")
            elif vericomm_output["scroll_up_down"] == 2:
                await page.evaluate("window.scrollBy(0, 200)")
        else:
            print("🚫 Skipping vericomm automatic scrolling - backlink agent handled scrolling")
            # Create a basic vericomm output for history when agent handled scrolling
            vericomm_output = {
                "action_verification": True,
                "next_action_suggestion": "Continue with next action",
                "scroll_up_down": 0,
                "anomaly_detected": "none"
            }
        
        # Build history element
        fields_filled = [f["id"] for f in elements_input] if elements_input else []
        scroll_position = await page.evaluate("window.scrollY")
        anomaly_description = vericomm_output.get("anomaly_detected", "")
        
        history_element = {
            "action_taken": agent_result["action_taken"],
            "action_successful_yes_no": vericomm_output["action_verification"],
            "next_action_suggestion": vericomm_output["next_action_suggestion"],
            "page_url": page.url,
            "fields_filled": fields_filled,
            "scroll_position": scroll_position,
            "anomaly_detected": anomaly_description
        }
        
        # Handle anomalies
        if anomaly_description and anomaly_description.lower() != 'none':
            for entry in reversed(history_list):
                if (entry["action_taken"] == agent_result["action_taken"] and 
                    not entry.get("invalidated")):
                    entry["invalidated"] = True
                    entry["anomaly_note"] = f"This action is being retried due to anomaly: {anomaly_description}"
                    break
            
            history_list.append({
                "action_taken": agent_result["action_taken"],
                "note": f"Action is being retried due to anomaly: {anomaly_description}",
                "anomaly_detected": anomaly_description
            })
        
        history_list.append(history_element)
        message_history.extend(temp_message)
        
        # Check if process completed
        if agent_result.get("process_status"):
            break
        
        i += 1
    
    print("================================== END BACKLINK CREATOR AGENT ==================================")
    return page, agent_result.get("process_status", False)
