from agents.base_agent import BaseAgent
import easyocr
import torch
import asyncio
import os
from urllib.parse import urlparse
from dotenv import load_dotenv
from utils.captcha_handler import wait_for_captcha_resolution
from utils.playwright_functions import cross_reference, click, fill_fields
from utils.annotate_functions import annotate_page
from utils.close_popup import click_highest_confidence_text
from agents.gmail_agent import get_email_instructions, compare_agent
from agents.verification_agent import vericomm_agent

load_dotenv()

class LoginAgent(BaseAgent):
    """Login agent for handling directory login/signup processes."""
    
    def get_tool_schema(self) -> list:
        """Return the tool schema for login agent."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "submit_directory_action",
                    "description": "Decide which interactive elements to click or fill to progress the signup flow on a directory page.",
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
                                "description": "True if the login process is complete and the user is successfully logged into their account. Only set to true when you can clearly see logged-in indicators like dashboard, profile, logout options, etc."
                            },
                            "check_email": {
                                "type": "boolean",
                                "description": "Set to true ONLY if you can clearly see explicit text on the screen indicating email verification is required, such as 'Check your email for verification link', 'OTP sent to your email', 'Verification code sent to email', 'Please check your email for confirmation', etc. DO NOT set to true based on assumptions or if just completing a form without explicit email verification message."
                            },
                            "captcha_detected": {
                                "type": "boolean",
                                "description": "Set to true ONLY if you can clearly see a captcha challenge on the screen (reCAPTCHA, hCaptcha, image verification, puzzle solving, etc.). The captcha solving system will then be activated to handle it automatically. DO NOT set to true unless you can visually confirm a captcha is present on the page."
                            },
                            "scroll_needed": {
                                "type": "boolean",
                                "description": "Set to true ONLY if all visible form elements are completely filled/selected and all required checkboxes are checked, but essential buttons (Submit/Continue/Next/Senden/Weiter) are missing from the current viewport. DO NOT scroll if there are any unfilled fields, empty dropdowns, or unchecked required checkboxes visible."
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
                        "required": ["popup", "click", "write", "order", "action_taken", "process_status", "scroll_needed", "scroll_direction"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "fetch_email_verification",
                    "description": "Fetch the latest email content including verification URLs and OTP codes for email verification during signup/login process.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "content_type": {
                                "type": "string",
                                "enum": ["url", "otp", "both", "latest"],
                                "description": "Type of content to extract: 'url' for verification links, 'otp' for verification codes, 'both' for both URL and OTP, 'latest' for full email content"
                            },
                            "email_count": {
                                "type": "integer",
                                "default": 1,
                                "description": "Number of recent emails to check (default: 1, max: 5)"
                            }
                        },
                        "required": ["content_type"]
                    }
                }
            }
        ]
    
    def get_agent_prompt(self) -> str:
        """Return the system prompt for login agent."""
        return f"""
    You are a world-class AI automation engine and are adept at signing up onto websites and directories. You are based in Germany and fluent in German. The directories you will sign up onto would primarily be in German.

    ## Main goal
    # Analyze the given image and the given list of interactive elements that you can see on the image. You need to determine which of these are responsible for propagating the navigation through the given directory webpage. It is important that you pay attention to the image for getting the appropriate context and the interactive elements list for which values to click. You are tasked with helping me first signup to this given current directory, and then subsequently register my business on that. You are also given a list of interactible elements {{list}} and current browser tabs information {{tabs_info}}.
    You need to perform click or fill actions - click in case of button-like interactible elements (remember they are in German), and fill in case of form-like interactible elements. You are also given a thorough history through a list of commands that tell you about: (a) the actions that you took, (b) if those actions passed or failed, (c) suggestion provided by the expert on what to do next. You need to treat this historical record as a reference and allow it to guide you in order to determine what to do next.
    
    **CRITICAL**: Form elements include BOTH input fields AND dropdown/select fields. When you see elements with tag 'select', these are dropdown menus that must be filled with appropriate values (e.g., gender selection, country selection, etc.). Do NOT skip any form elements!
    
    The tabs_info provides you with complete context about all open browser tabs including their URLs, titles, current status, and which tab is currently active. Use this information for contextual awareness during the login process.
    
        
        
    BUSINESS_DATA = {self.get_business_data_json()}
    Assume/deduce all remaining information that might be required.
    

    ## Step-by-step plan
    1. **Historical Analysis**
        Take into account the historical records that are given to you, learn from your mistakes and implement the suggestions given to you ALONG WITH your own reasoning so as to move forward with the most logically sound step, and create a solid action plan regarding what to do right now.
    2. **Tab Context Analysis**
        Review the tabs_info to understand the current browser state. Check what tabs are open, which one is currently active, and whether there are any relevant tabs (like email verification, signup pages, etc.) for context and situational awareness.
    3. **Image Analysis**  
        Take a deep look at the image. Remember to detect any and all popups; if it is, return true. A popup is a rare occurrence, but it can happen. The image of the automation process usually should contain the image of a webpage and the annotated, numbered bounding boxes of the interactible elements.
        You need to determine based on the history given to you and the main goal of the task, what action you should take now, and by action I mean which of the interactible elements
        you should interact with (i.e. click a button/fill in some value)
    4. **Things to keep in mind**
        You need to keep in mind that this entire procedure is for signing up and logging into said directory, so it goes without saying that your initial actions should be oriented towards signing up for the given directory by using the email ID I provided.
        After you can clearly see in the history that login was successful, should you be satisfied.
    5. **Implementing Action**
        When you have decided what you need to do, simply do that by sharing which element of all numbered ones to interact with, and keep in mind that sometimes, we need to click a button before entering text,
        or enter some text and THEN click a button. These minute things matter, so it'll be good if you share the order as well. Other than that, there should not be a lot of buttons to choose from; the ones responsible for logging in/submitting/filling crucial info should be obvious.
        
        **IMPORTANT - Dropdown/Select Fields**: When you see elements with tag 'select', these are dropdown fields that MUST be filled with appropriate values:
        - For gender/anrede dropdowns (like "keine Angabe Frau Herr"), choose "Herr" for male or "Frau" for female based on business data
        - For country/land dropdowns, always select "Deutschland" unless specified otherwise
        - For any other dropdowns, select the most appropriate option based on the available choices and business context
        - ALWAYS include dropdown elements in your 'write' array with [element_id, selected_value] format
        
        **IMPORTANT - Checkbox/Consent Fields**: When you see checkbox elements (usually for consent, agreements, terms, etc.):
        - These are typically agreement checkboxes like "I agree to terms", "I consent to data processing", "Accept privacy policy"
        - For consent/agreement checkboxes, use "true" or "checked" as the value to check them
        - For data processing consent (GDPR), promotional emails, or similar optional checkboxes, use "true" to accept
        - ALWAYS include checkbox elements in your 'write' array with [element_id, "true"] format for agreements
        - Common checkbox text includes: "einverstanden", "zustimmen", "akzeptieren", "willige ein", "agree", "consent", "accept"
    6. **Watch out for email verification - USE ONLY WHEN EXPLICITLY REQUIRED**
        ONLY set check_email to true if you can clearly see one of these EXPLICIT messages on the screen:
        - "Check your email for verification link" / "Überprüfen Sie Ihre E-Mail für den Bestätigungslink"
        - "OTP sent to your email" / "OTP an Ihre E-Mail gesendet"
        - "Verification code sent to email" / "Bestätigungscode an E-Mail gesendet"
        - "Please check your email for confirmation" / "Bitte überprüfen Sie Ihre E-Mail zur Bestätigung"
        - "Email verification required" / "E-Mail-Verifizierung erforderlich"
        - "We have sent you an email" / "Wir haben Ihnen eine E-Mail gesendet"
        - Any similar explicit message indicating email verification is needed
        
        When email verification IS explicitly required:
        - Set check_email to true in your response to indicate email verification is needed
        - The system will automatically fetch the latest email content
        - You'll receive the verification URL and/or OTP code to proceed with the process
        - Use the fetched URL to navigate or the OTP code to fill in verification fields
    7. **Indications for process completion**
        If you ever encounter a page that indicates the login process is complete (like seeing dashboard, profile options, logout button, "mein konto", "abmelden", etc.), 
        go ahead and mark the process as completed by setting process_status to true in the JSON response. 
        IMPORTANT: Once you set process_status to true, DO NOT take any further actions. Your job as the login agent is complete.
    8.  **Signup THEN register business**
        Depending on the history that is passed to you, you need to make sure that the signup process is completed before starting to think about registering the business.
    9.  **Know the difference between registration and signup**
        It can be confusing to determine what to click when faced with 2 buttons, one suggesting login other register. ALWAYS REMEMBER TO CLICK THE LOGIN BUTTON / BUTTONS THAT SUGGEST THAT THEY ARE FOR LOGGING IN, NOT REGISTERING BUSINESS, like 'try for free' or 'test it out' or 'contact us'. If you see signup option go for that, but if login requires pre-existing account go for next most viable option.
    10. **CAPTCHA DETECTION**
        If you can clearly see a captcha challenge on the page (reCAPTCHA, hCaptcha, image verification puzzles, "I'm not a robot" checkboxes, etc.), set captcha_detected to true. The automated captcha solving system will then be activated to handle it. Only set this when you can visually confirm a captcha is present - do not assume based on loading states or other factors.
    11. **WHEN LOGIN IS COMPLETE, STOP!**
        Your role is ONLY to handle login/signup. Once a user is successfully logged in (dashboard visible, profile accessible, etc.), 
        set process_status to true and do NOT click on any business registration or "add company" buttons. That is the job of the registration agent.
    12. **Smart Scrolling Control**
        You now have the ability to control page scrolling when needed:
        
        **CRITICAL SCROLLING PRIORITY RULES:**
        
        **PRIORITY 1 - DO NOT SCROLL IF VISIBLE ELEMENTS NEED COMPLETION:**
        **NEVER scroll if the current viewport contains any:**
        - Empty/unfilled form fields (text boxes, dropdowns, etc.)
        - Unchecked required checkboxes or radio buttons
        - Unselected dropdown menus
        - Any other interactive elements that still need user input
        
        **PRIORITY 2 - SCROLL ONLY WHEN ALL VISIBLE ELEMENTS ARE COMPLETE:**
        **A. Form Completion Without Submit Option:** If ALL visible form fields are FILLED/COMPLETED and ALL checkboxes are properly checked, but no submit/continue button is visible in the current viewport, set scroll_needed to true to find the submission mechanism.
        
        **B. Repeated Failed Actions:** If the same action is being attempted multiple times with no visible change, ALL visible elements are complete, and the target element (button/link) is not visible in the current view, set scroll_needed to true to locate the correct interactive element.
        
        **Direction Logic:**
        - Use 'down' if looking for submit buttons, continue buttons, or elements typically at the bottom of forms
        - Use 'up' if looking for navigation elements, headers, error messages or elements typically at the top
        - Use 'none' when no scrolling is needed
        
        **Setting scroll_needed and scroll_direction:**
        - Only set scroll_needed to true when ALL visible form elements are completely filled and essential buttons are missing
        - Provide a clear scroll_reason explaining your decision
        - The scrolling will be executed automatically based on your decision
    ## Guidelines
    * Always enter the correct details that you have to write about the elements that should be interacted with  
    * Always respect the history and the main task at hand, and make decisions according to what is required and what has been accomplished to-date, along with what needs to be accomplished  
    * Keep an eager eye out for email verification requirement; this step will only come once in the entire cycle, but is important to be dealt with ONLY when explicitly requested by the page with clear text messages.
    * CRITICAL EMAIL VERIFICATION RULE: Only set check_email to true if you can see explicit text on the page mentioning email verification, OTP sent to email, or checking email for links. Do NOT assume email verification is needed just because you completed a signup form.
    * After making all the decisions regarding which step to take, write down the overall action that you took and return under action_taken. Return completed if goal is achieved.
    * If ever encountered with numerous possible options for proceeding towards signup/register business, always choose the free tier option/free plan 
    * Always use the history as reference 
    * If the buttons themselves don't have any text on them try to click the ones that are nearby the relevant text
    * Do not repeat an action for more than 3 times in a row. Invent new strategies to move forward if you see the same action repeated in the history.
    * If you encounter a place to insert text where you don't know what to write / not given in business data then just make a guess
    * Keep an eye out for any elements that carry the filled tag; if it is true then don't bother filling that particular element, it means it is preselected
    * Always click on SIGNUP/LOGIN or related buttons first, always. If you see an option to signup then go for that, else go to the next best option
    * PLEASE MAKE SURE TO CHECK ALL ACKNOWLEDGEMENT BOXES / I AGREE BOXES / I CONSENT BOXES and other similar check-boxes.
    * **DROPDOWN FIELDS REQUIREMENT**: For ANY element with tag 'select' (dropdown menus), you MUST include them in your 'write' array. Common dropdowns include gender/anrede (select "Herr" or "Frau"), country/land (select "Deutschland"), and other selection fields. Do NOT skip dropdown fields!
    * **CHECKBOX FIELDS REQUIREMENT**: For ANY checkbox/consent elements, you MUST include them in your 'write' array with "true" as the value to check them. This includes privacy policy agreements, terms of service, data processing consent, marketing emails, etc. Look for text like "einverstanden", "zustimmen", "akzeptieren", "willige ein", "agree", "consent", "accept".
    * CRITICAL: Once you see the user is logged in (dashboard, profile, logout button visible), immediately set process_status to true and do NOT take any further actions. Do NOT click on "add company", "register business", or similar buttons - that is NOT your job!
    * **SCROLLING DECISION GUIDELINES**: Only set scroll_needed to true when ALL visible elements are completely filled/completed and essential buttons (Submit/Continue/Next) are missing from current view. Do NOT scroll if any visible form fields, dropdowns, or checkboxes still need completion. Always provide a clear scroll_reason for your decision.
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
                ] |list| (INCLUDE ALL form elements: input fields, select dropdowns, checkboxes with "true" for agreements, etc.),
        order : (1 if first click then input, 2 if first input then click, 3 if only click, 4 if only input) |int| ,
        action taken : what action was taken |str| ,
        process_status : True/False (only true when login is complete and user is logged in) |bool|,
        check_email : True/False (ONLY set to true when you can clearly see explicit text on screen indicating email verification is required) |bool|,
        captcha_detected : True/False (ONLY set to true when you can clearly see a captcha challenge on screen like reCAPTCHA, hCaptcha, image verification, etc.) |bool|,
        scroll_needed : True/False (ONLY set to true when all visible elements are filled but essential buttons are missing from viewport) |bool|,
        scroll_direction : "none"/"up"/"down" (direction to scroll when scroll_needed is true) |str|,
        scroll_reason : "explanation for scrolling decision" |str|
    }}
    
    ## Email Verification Integration
    When you set check_email to true, an AI email analysis agent will:
    1. Fetch the latest email from your inbox
    2. Analyze the content using AI to determine verification steps
    3. Provide specific instructions like "Navigate to URL: ..." or "Fill OTP: ..."
    4. Automatically handle URL navigation or provide OTP codes
    5. Give you contextual guidance on next steps
    
    The email agent is intelligent and will understand the context - you just need to request email analysis when verification is needed.
    """


# Create instance and function for backward compatibility
login_agent_instance = LoginAgent()

def login_agent(image_path: str, user_prompt: str, message_history: list, debug: bool = False, website_context: str = ""):
    """
    Backward compatible function for login agent.
    
    Args:
        image_path: Path to screenshot image
        user_prompt: User prompt with elements data
        message_history: Previous conversation history
        debug: Whether to print debug information
        website_context: Current website context for email analysis
        
    Returns:
        Tuple of (data_uri, agent_result)
    """
    return login_agent_instance.execute(image_path, user_prompt, message_history, debug, website_context)


async def is_verification_email_related_to_site(page, email_content):
    """
    Check if a verification email is related to the current site using the compare agent.
    
    Args:
        page: Current page object to extract website content
        email_content: Email content to compare
        
    Returns:
        Boolean indicating if the email is related to the current site
    """
    try:
        # Extract website text content from the current page
        website_text = await page.evaluate("""
            () => {
                // Get the main content, focusing on visible text
                const body = document.body;
                if (!body) return "";
                
                // Remove script and style elements
                const scripts = body.querySelectorAll('script, style, noscript');
                scripts.forEach(el => el.remove());
                
                // Get text content and clean it up
                let text = body.innerText || body.textContent || "";
                
                // Clean up the text - remove excessive whitespace
                text = text.replace(/\\s+/g, ' ').trim();
                
                // Limit to first 1000 characters to avoid too much noise
                return text.substring(0, 1000);
            }
        """)
        
        if not website_text or not email_content:
            print("⚠️ Missing website text or email content for comparison")
            return False
        
        # Use the compare agent from gmail_agent
        comparison_result = compare_agent(website_text, email_content)
        
        is_related = comparison_result.get('related', False)
        
        if is_related:
            print(f"✅ Email verified as related to current site")
            print(f"📄 Website domain: {urlparse(page.url).netloc}")
        else:
            print(f"🚫 Email not related to current site")
            print(f"📄 Website domain: {urlparse(page.url).netloc}")
            print(f"📧 Email content preview: {email_content[:200]}...")
            print(f"🔍 Compare agent determined the email content is not contextually related to the current website")
        
        return is_related
        
    except Exception as e:
        print(f"❌ Error checking email-site relationship: {e}")
        # In case of error, be conservative and return False
        return False


async def get_browser_tabs_info(browser, current_page):
    """
    Get information about all open tabs in the browser.
    
    Args:
        browser: Browser context
        current_page: Currently active page
        
    Returns:
        Dictionary containing tab information
    """
    tabs_info = {
        "current_tab_index": -1,
        "total_tabs": 0,
        "tabs": []
    }
    
    try:
        pages = browser.pages
        tabs_info["total_tabs"] = len(pages)
        
        for i, page in enumerate(pages):
            try:
                # Get basic page information
                page_url = page.url
                page_title = await page.title()
                is_current = page == current_page
                
                if is_current:
                    tabs_info["current_tab_index"] = i
                
                tab_info = {
                    "index": i,
                    "url": page_url,
                    "title": page_title,
                    "is_current": is_current,
                    "is_closed": page.is_closed()
                }
                
                tabs_info["tabs"].append(tab_info)
                
            except Exception as e:
                # Handle pages that might be in an invalid state
                print(f"[DEBUG] Error getting info for tab {i}: {e}")
                tab_info = {
                    "index": i,
                    "url": "unknown",
                    "title": "unknown",
                    "is_current": page == current_page,
                    "is_closed": True,
                    "error": str(e)
                }
                tabs_info["tabs"].append(tab_info)
    
    except Exception as e:
        print(f"[DEBUG] Error getting browser tabs info: {e}")
        tabs_info["error"] = str(e)
    
    return tabs_info


async def execute_login_loop(page, browser, MAX_ITERS, original_text_string, scroll_path):
    """
    Execute the login agent loop with email verification support.
    
    Returns:
        Tuple of (page, login_complete)
    """
    i = 0
    history_list = []
    message_history = []
    login_complete = False
    scroll = 0
    
    print("================================== START LOGIN AGENT ==================================")
    
    while i < MAX_ITERS:
        agent_inputs = [{"history": history_list}]
        
        # Initialize scrolling control variable for this iteration
        login_agent_handled_scroll = False
        
        # Handle closed pages
        if page.is_closed():
            pages = page.context.pages
            if not pages:
                raise RuntimeError("All tabs closed—nothing left to do.")
            page = pages[-1]
            print(f"[DEBUG] page was closed; switched to {page.url}")
        
        await page.wait_for_load_state('load')
        img_path, elements = await annotate_page(page)
        
        # Get current browser tabs information
        tabs_info = await get_browser_tabs_info(browser, page)
        
        if len(history_list) > 0:
            elements.extend(agent_inputs)
        elements_str = str(elements)
        
        # Prepare cleaned elements for agent including tabs info
        cleaned_elements = [
            {
                'elements': [
                    {
                        'id': elem['id'], 
                        'tag': elem['tag'], 
                        'text': elem.get('text', '')[:200] if len(elem.get('text', '')) > 200 else elem.get('text', ''), 
                        'labelText': elem.get('labelText', '')[:200] if len(elem.get('labelText', '')) > 200 else elem.get('labelText', '')
                    } 
                    for elem in elements if 'id' in elem
                ]
            },
            {
                'tabs_info': tabs_info
            }
        ]
        cleaned_elements_str = str(cleaned_elements)

        # print("[DEBUG] cleaned_elements_str:", cleaned_elements_str)
        # Write debug logs to a file instead of printing
        debug_log_path = os.path.join(os.getcwd(), "login_agent_debug.log")
        with open(debug_log_path, "a", encoding="utf-8") as debug_log_file:
            debug_log_file.write(f"[DEBUG] cleaned_elements_str: {cleaned_elements_str}\n")
            debug_log_file.write(f"[DEBUG] elements_str: {elements_str}\n")
        
        # Call the login agent with website context
        website_context = f"Current URL: {page.url}, Original text: {original_text_string[:200]}"
        prev_img_uri, agent_result = login_agent(img_path, cleaned_elements_str, message_history, True, website_context)
        
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
                print("✅ Successfully clicked popup acceptance button")
                continue
            else:
                print("⚠️ Minor popup detected but could not click, can be ignored")
        
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
        
        # Get cross-referenced elements for actions (only if we have a valid action result)
        if 'order' in agent_result:
            elements_click, elements_input = cross_reference(elements_only, agent_result)
        else:
            elements_click, elements_input = [], []
        
        # Execute actions based on order (only if order is present)
        if 'order' in agent_result:
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
        
        # Handle login agent scrolling decisions
        if agent_result.get("scroll_needed") and agent_result.get("scroll_direction") != "none":
            scroll_direction = agent_result.get("scroll_direction", "none")
            scroll_reason = agent_result.get("scroll_reason", "No reason provided")
            
            print(f"📜 Login Agent Scrolling: {scroll_direction} - Reason: {scroll_reason}")
            
            if scroll_direction == "up":
                await page.evaluate("window.scrollBy(0, -200)")
                print("⬆️ Scrolled up by 200px per login agent decision")
            elif scroll_direction == "down":
                await page.evaluate("window.scrollBy(0, 200)")
                print("⬇️ Scrolled down by 200px per login agent decision")
            
            # Add scroll action to history
            history_list.append({
                "action_taken": f"login_agent_scroll_{scroll_direction}",
                "status": "executed",
                "reason": scroll_reason,
                "scroll_direction": scroll_direction
            })
            
            # Wait for scroll to complete and page to stabilize
            await asyncio.sleep(1)
            await page.wait_for_load_state('load')
            
            # Skip verification agent for this iteration since login agent handled scrolling
            login_agent_handled_scroll = True
        else:
            login_agent_handled_scroll = False
        
        # Handle email verification analysis (now properly async)
        if agent_result.get('check_email') or (agent_result.get('email_analysis') and agent_result['email_analysis'].get('email_verification_requested')):
            print("# =================== Processing Email Verification ===================")
            
            website_context = f"Current URL: {page.url}, Original text: {original_text_string[:200]}"
            try:
                email_analysis = await get_email_instructions(website_context)
                if email_analysis and not email_analysis.get('error'):
                    print(f"📧 Email Analysis Complete: {email_analysis.get('instructions', 'No instructions')}")
                    
                    action_type = email_analysis.get('action_type')
                    instructions = email_analysis.get('instructions', '')
                    
                    if action_type == 'navigate_url' and email_analysis.get('verification_url'):
                        verification_url = email_analysis['verification_url']
                        email_content = email_analysis.get('full_email_text', '')
                        
                        # Check if verification email is related to current site using compare agent
                        if await is_verification_email_related_to_site(page, email_content):
                            print(f"🔗 Opening verified related URL: {verification_url}")
                            
                            verification_page = await browser.new_page()
                            try:
                                await verification_page.goto(verification_url, timeout=30000)
                                page = verification_page
                                print("✅ Successfully navigated to verification URL")
                                
                                history_list.append({
                                    "action_taken": f"email_verification_url_opened: {verification_url}",
                                    "note": f"AI Email Agent Instructions: {instructions}",
                                    "status": "success"
                                })
                            except Exception as e:
                                print(f"❌ Failed to navigate to verification URL: {e}")
                                await verification_page.close()
                                history_list.append({
                                    "action_taken": "email_verification_url_failed",
                                    "error": str(e),
                                    "status": "failed"
                                })
                        else:
                            print(f"🚫 Verification email rejected - not related to current site: {verification_url}")
                            print(f"📍 Current site: {page.url}")
                            history_list.append({
                                "action_taken": "email_verification_url_rejected",
                                "verification_url": verification_url,
                                "current_url": page.url,
                                "reason": "Email content not related to current site",
                                "note": f"AI Email Agent Instructions: {instructions}",
                                "status": "skipped"
                            })
                    
                    elif action_type == 'fill_otp' and email_analysis.get('otp_code'):
                        otp_code = email_analysis['otp_code']
                        print(f"📧 OTP received for next iteration: {otp_code}")
                        
                        history_list.append({
                            "action_taken": "email_verification_otp_received",
                            "otp_code": otp_code,
                            "note": f"AI Email Agent Instructions: {instructions}",
                            "status": "success"
                        })
                    
                    elif action_type == 'both_available':
                        priority = email_analysis.get('priority_action', 'url')
                        if priority == 'url' and email_analysis.get('verification_url'):
                            verification_url = email_analysis['verification_url']
                            email_content = email_analysis.get('full_email_text', '')
                            
                            # Check if verification email is related to current site using compare agent
                            if await is_verification_email_related_to_site(page, email_content):
                                print(f"🔗 Prioritizing verified related URL navigation: {verification_url}")
                                verification_page = await browser.new_page()
                                try:
                                    await verification_page.goto(verification_url, timeout=30000)
                                    page = verification_page
                                    print("✅ Successfully navigated to verification URL")
                                    
                                    history_list.append({
                                        "action_taken": f"email_verification_url_opened_priority: {verification_url}",
                                        "note": f"AI Email Agent Instructions: {instructions}",
                                        "status": "success"
                                    })
                                except Exception as e:
                                    print(f"❌ URL navigation failed, will use OTP instead: {e}")
                                    await verification_page.close()
                                    # Fall back to OTP if available
                                    if email_analysis.get('otp_code'):
                                        otp_code = email_analysis['otp_code']
                                        print(f"📧 Falling back to OTP due to URL failure: {otp_code}")
                                        history_list.append({
                                            "action_taken": "email_verification_fallback_to_otp",
                                            "otp_code": otp_code,
                                            "note": f"URL failed, using OTP. Instructions: {instructions}",
                                            "status": "success"
                                        })
                            else:
                                print(f"🚫 Priority email rejected - not related to current site: {verification_url}")
                                print(f"📍 Current site: {page.url}")
                                # Use OTP instead if available
                                if email_analysis.get('otp_code'):
                                    otp_code = email_analysis['otp_code']
                                    print(f"📧 Using OTP instead of unrelated email: {otp_code}")
                                    history_list.append({
                                        "action_taken": "email_verification_otp_due_to_unrelated_email",
                                        "otp_code": otp_code,
                                        "rejected_url": verification_url,
                                        "current_url": page.url,
                                        "note": f"Email rejected, using OTP. Instructions: {instructions}",
                                        "status": "success"
                                    })
                                else:
                                    history_list.append({
                                        "action_taken": "email_verification_email_rejected_no_otp",
                                        "verification_url": verification_url,
                                        "current_url": page.url,
                                        "reason": "Email content not related to current site and no OTP available",
                                        "note": f"AI Email Agent Instructions: {instructions}",
                                        "status": "failed"
                                    })
                        elif email_analysis.get('otp_code'):
                            otp_code = email_analysis['otp_code']
                            print(f"📧 Using OTP for verification: {otp_code}")
                            history_list.append({
                                "action_taken": "email_verification_otp_ready",
                                "otp_code": otp_code,
                                "note": f"AI Email Agent Instructions: {instructions}",
                                "status": "success"
                            })
                else:
                    print("❌ Email analysis failed or no verification email found")
                    history_list.append({
                        "action_taken": "email_verification_failed",
                        "error": email_analysis.get('error', 'No email found') if email_analysis else 'Email fetch failed',
                        "status": "failed"
                    })
            except Exception as e:
                print(f"❌ Email verification error: {e}")
                history_list.append({
                    "action_taken": "email_verification_error",
                    "error": str(e),
                    "status": "failed"
                })
        
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
        
        
        # Check if agent marked login as complete BEFORE verification
        if agent_result.get("process_status"):
            print("# =================== Login Agent Marked Process as Complete ===================")
            print("✅ LOGIN SUCCESSFUL - Exiting login agent loop")
            print("🔄 Control will now be passed to registration agent")
            login_complete = True
            # Add minimal history entry and break immediately
            completion_tabs_info = await get_browser_tabs_info(browser, page)
            completion_action_taken = agent_result.get("action_taken", "login_completed")
            history_element = {
                "action_taken": completion_action_taken,
                "action_successful_yes_no": "yes",
                "next_action_suggestion": "Login process completed successfully - ready for registration",
                "page_url": page.url,
                "fields_filled": [],
                "scroll_position": await page.evaluate("window.scrollY"),
                "tabs_state": {
                    "total_tabs": completion_tabs_info["total_tabs"],
                    "current_tab_index": completion_tabs_info["current_tab_index"],
                    "current_tab_url": page.url
                },
                "anomaly_detected": "None"
            }
            history_list.append(history_element)
            message_history.extend(temp_message)
            break
        
        # Verification and history update (only when login not complete)
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
        
        # Ensure agent_result has required fields before proceeding
        if not isinstance(agent_result, dict):
            print(f"⚠️ Agent result is not a dictionary: {type(agent_result)}")
            agent_result = {"action_taken": "invalid_response", "order": -1}
        
        # Provide default values for required keys
        action_taken = agent_result.get("action_taken", "no_action_specified")
        
        # Call verification agent only if login agent didn't handle scrolling
        if not login_agent_handled_scroll:
            vericomm_output = vericomm_agent(img_path, img_path_new, current_scroll_path, 
                                                history_list, current_action=action_taken)
            print("======================== VERIFIER OUTPUT (start) ========================")
            print(vericomm_output)
            print("======================== VERIFIER OUTPUT (end) ========================")
            
            if vericomm_output["scroll_up_down"] == 1:
                await page.evaluate("window.scrollBy(0, -200)")
                print("⬆️ Verification agent scrolled up by 200px")
            elif vericomm_output["scroll_up_down"] == 2:
                await page.evaluate("window.scrollBy(0, 200)")
                print("⬇️ Verification agent scrolled down by 200px")
            
            action_verification = vericomm_output["action_verification"]
            next_action_suggestion = vericomm_output["next_action_suggestion"]
            anomaly_description = vericomm_output.get("anomaly_detected", "")
        else:
            print("📜 Skipping verification agent - Login agent handled scrolling decision")
            # Create a simple verification output when login agent handled scrolling
            vericomm_output = {
                "action_verification": "yes",  # Assume success since login agent made intelligent decision
                "next_action_suggestion": f"Continue with form completion after login agent scroll {agent_result.get('scroll_direction', 'unknown')}",
                "scroll": f"Login agent handled scrolling: {agent_result.get('scroll_reason', 'No reason provided')}",
                "scroll_up_down": -1,  # No additional scrolling needed
                "anomaly_detected": "None",
                "outcome_summary": f"Login agent controlled scrolling: {agent_result.get('scroll_direction', 'none')}"
            }
            action_verification = "yes"
            next_action_suggestion = vericomm_output["next_action_suggestion"]
            anomaly_description = "None"
        
        # Build history element
        fields_filled = [f["id"] for f in elements_input] if elements_input else []
        scroll_position = await page.evaluate("window.scrollY")
        
        # Get current tab state for history
        current_tabs_info = await get_browser_tabs_info(browser, page)
        
        history_element = {
            "action_taken": action_taken,
            "action_successful_yes_no": action_verification,
            "next_action_suggestion": next_action_suggestion,
            "page_url": page.url,
            "fields_filled": fields_filled,
            "scroll_position": scroll_position,
            "tabs_state": {
                "total_tabs": current_tabs_info["total_tabs"],
                "current_tab_index": current_tabs_info["current_tab_index"],
                "current_tab_url": page.url
            },
            "anomaly_detected": anomaly_description
        }
        
        # Add login agent scrolling information if applicable
        if login_agent_handled_scroll:
            history_element["login_agent_scroll"] = {
                "scroll_needed": agent_result.get("scroll_needed", False),
                "scroll_direction": agent_result.get("scroll_direction", "none"),
                "scroll_reason": agent_result.get("scroll_reason", "No reason provided")
            }
        
        # Handle anomalies
        if anomaly_description and anomaly_description.lower() != 'none':
            for entry in reversed(history_list):
                if (entry["action_taken"] == action_taken and 
                    not entry.get("invalidated")):
                    entry["invalidated"] = True
                    entry["anomaly_note"] = f"This action is being retried due to anomaly: {anomaly_description}"
                    break
            
            history_list.append({
                "action_taken": action_taken,
                "note": f"Action is being retried due to anomaly: {anomaly_description}",
                "anomaly_detected": anomaly_description
            })
        
        history_list.append(history_element)
        message_history.extend(temp_message)
        
        i += 1
    
    print("================================== END LOGIN AGENT ==================================")
    return page, login_complete
