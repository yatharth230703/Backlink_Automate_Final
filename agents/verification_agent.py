from openai import OpenAI
import base64
import json
from dotenv import load_dotenv
from itertools import chain 
load_dotenv()


## basis of this agent would be something like 
## login wale ne action lia , start me popup khudse resolve hojaega , and uske baad har entry post-action ispe jaegi
## action lene k baad ka screenshot -- 2 states : either new page with nothing filled -->this would mean I clicked something / did something and just landed here, or I was unable to do anything and landed where I BEGAN??
                                             # same page with some values input --> this would mean I need to scroll 
                                             # should I have 2 image inputs ? one before action and one after ? I think yes
                                             # so now I have 2 images , one before action and one after action , this would prompt my agent to choose what to do next .It can : 
                                             # verify the action in accordance to gmail agent : if processed then give control to the register agent , if unsuccessful (no URL , but email_verification= true) return exception .If not reqd (email verification false) then continue control of login agent
                                             # verify the action in accordance to the history + future action part of agent's most recent response : was it successful or something undesireable happened ? 
                                             # if it was successful , do you think it requires further scrolldown / scrollup ? if so , scrolldown/scrollup by 200px . If not , continue loop 
                                             # maintain 2 image variables , one before action and one after action , kinda like temp and prev in linkedlist
                                              
import os 
tool_schema = [
    {
        "type": "function",
        "function": {
            "name": "verification-action",
            "description": "Take a look at the history of the actions agent {another agent responsible for controlling the web automation} and the before/ after screenshots of a page ,you need to deduce various aspects of the scenario the current step of web-automation is faced with.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action_verification" : {
                        "type" : "string",
                        "enum" : ["yes" ,"no"],
                        "description" : "Based on the historical decisions list of the actions taken by agent , the current action taken by agent and the before and after screenshot of the current page , determine if the intended action was completed or not. An incomplete action might be something that requires scrolling-into-view some other elements , clicking a different button than the one clicked previously , performing another action etc . A complete action is determined by cross referencing history with the before and after screenshots of the page, if the intended action took place (button clicked / all values entered) then it was a complete action. Return yes for completed action / successful action , no for incomplete action/ unsuccessful action."
                    },
                    "next_action_suggestion" : {
                         "type" : "string" ,
                         "description": "Based on the historical decisions list of the actions taken by agent , the current action taken by agent and the before and after screenshot of the current page , suggest what should the agent do next in order to move the entire process one step closer to completion. CRITICAL: If authentication errors are detected (account exists on signup → suggest login, account not found on login → suggest signup), prioritize flow switching over other actions. Don't recommend scrolling because if it is required , it will happen automatically just after this agent call. Anything else is welcome. Assume scrolling is already executed {if it was requred} ,what next "  
                    },
                    "scroll": {
                        "type": "string",
                        "description": "CRITICAL: Determine if scrolling is required with strict priority rules. PRIORITY 1: Do NOT scroll if there are any unfilled form fields, empty text boxes, or unchecked required checkboxes visible in the current viewport - these must be completed first. PRIORITY 2: Only scroll if ALL visible elements are filled/completed AND essential buttons (Submit/Senden/Continue/Next) are missing from current viewport but shown in the full webpage image. PRIORITY 3: Authentication errors requiring flow switching (signup ↔ login) override scrolling decisions. Return a 1-2 line justification explaining your decision based on these priorities."
                    },
                    "scroll_up_down": {
                        "type": "integer",
                        "enum": [-1, 1, 2 ],
                        "description": "-1: no scrolling , 1: scroll up, 2: scroll down"
                    },
                    "anomaly_detected": {
                        "type": "string",
                        "description": "Describe any anomaly or unexpected behavior detected during the verification process, such as no visible change after an action, unexpected page state, repeated popups, or anything else unusual. If no anomaly is detected, return an empty string or 'None'."
                    },
                    "outcome_summary": {
                        "type": "string",
                        "description": "A brief summary of the outcome. If an error or success message is visible in the 'after' image, quote it here. Example: 'Login fehlerhaft! Bitte versuchen Sie es noch einmal...' or 'Registration successful.' If no new message is visible, state 'No new message detected.'"
                    }
                },
                "required": ["action_verification" ,"next_action_suggestion","scroll", "scroll_up_down", "outcome_summary"]
            }
        }
    }
]

### add scroll and scroll up down to history as well , action verification bhi .

first_AGENT_PROMPT="""
    You are a world-class AI automation engine and are adept at navigating websites and directories. You are working with another actions agent that is responsible for taking action. Your role is primarily to verify those actions and make sure that the entire process is going towards the right direction. The directories you will navigate in would primarily be in German.

    ## Main goal
    # Analyze the given images which are before and after the action agent took place. These are screenshots of a page before and after the outputs of the action-agent was enacted on it. You are also given a historical record of what has happened till date, and verify if the images are in accordance to what you see in the before and after page-screenshots.
    You need to verify the action taken and determine if scrolling is necessary or not. To facilitate your decision making process regarding whether to scroll or not, you are provided with a third image that showcases the entire webpage at once; this way you will be able to determine whether scrolling further is required or not, even after elements might appear to be fully interacted-with.
    Scrolling is usually necessary in cases where you determine that either more input is required in terms of text (like filling out a long form) or the before page screenshot seems a lot like the after page screenshot, which tells us that the action did not take place, likely due to the interactive element responsible for propagating us forward would have been outside of current window, which again, warrants scrolling. If it is up or down that's up to your discretion. 
    
    In addition, you must carefully read any new text, error, or success messages that appear on the 'after' image. If such a message is visible, quote it exactly in the outcome_summary field. If no new message is visible, state 'No new message detected.'
    
        
    
    You will return a json file that looks like the following : 
    
    {
        action_verification : (If action taken by action agent was successful or not depending on your analysis of history , current action taken and before/after screenshots . yes for completed/successful , no for incomplete / unsuccessful) |string|
        next_action_suggestion : (based on your intuition suggest what to do next ) |string|
        scroll: (your analysis of whether the current page needs to be scrolled up/down or not ) |string|  , 
        scroll_up_down : (if scrolling indeed is necessary then in which direction ? -1 for scrolling not necessary , 1 for scrolling up and 2 for scrolling down) |int| 
        anomaly_detected : (describe any anomaly or unexpected behavior detected during the verification process, such as no visible change after an action, unexpected page state, repeated popups, or anything else unusual. If no anomaly is detected, return an empty string or 'None') |string|
        outcome_summary : (A brief summary of the outcome. If an error or success message is visible in the 'after' image, quote it here. Example: 'Login fehlerhaft! Bitte versuchen Sie es noch einmal...' or 'Registration successful.' If no new message is visible, state 'No new message detected.') |string|
    }
    ## Step-by-step plan
    1. **History-Images cross referencing **  
        You will be given the history of actions taken by the action agent , the action taken by the agent currently , along with the before and after image of the last action that took place. You need to analyze them both thoroughly so that you are able to determine if the action taken was indeed successful or not . 
    
    2. **Things to keep in mind**
        You need to be mindful of the differences between the before and after images. You should be able to notice the action just by seeing the difference between the images, whether a button was clicked and it took you to a different page, some amount of text was entered, etc. This will help you determine if the action was successful or not and allow you to decide whether more scrolling on that particular page is required or not.

    3. **Implementing scrolling**
    You are provided with a third image that showcases the full webpage layout. Cross-reference this with the after-image to determine if more elements are present **below or above** the current view.
        
        **CRITICAL SCROLLING PRIORITY RULES:**
        
        **PRIORITY 1 - DO NOT SCROLL IF VISIBLE ELEMENTS NEED COMPLETION:**
        **NEVER scroll if the current viewport (after-image) contains any:**
        - Empty/unfilled form fields (text boxes, dropdowns, etc.)
        - Unchecked required checkboxes or radio buttons
        - Unselected dropdown menus
        - Any other interactive elements that still need user input
        
        **PRIORITY 2 - SCROLL ONLY WHEN ALL VISIBLE ELEMENTS ARE COMPLETE:**
        **A. Form Completion Without Submit Option:** If ALL visible form fields are FILLED/COMPLETED and ALL checkboxes are properly checked, but no submit/continue button is visible in the current viewport, scroll to find the submission mechanism.
        
        **B. Repeated Failed Actions:** If the same action is being attempted multiple times with no visible change, ALL visible elements are complete, and the target element (button/link) is not visible in the current view, scroll to locate the correct interactive element.
        
        **PRIORITY 3 - AUTHENTICATION ERRORS OVERRIDE SCROLLING:**
        If authentication errors are detected that require flow switching (signup ↔ login), do not scroll regardless of other conditions.
        
        **Direction Logic:**
        - Scroll DOWN (2) if looking for submit buttons, continue buttons, or elements typically at the bottom of forms
        - Scroll UP (1) if looking for navigation elements, headers, error messages or elements typically at the top
        - Use the full webpage image to determine the location of missing elements

    4. **Making suggestions**
        When making suggestions as to what should be done next, keep in mind all the various inputs given and make sure to not suggest simply scrolling, as that will already be executed if need be.
    
    5. **Comprehensive Error Handling and Flow Control**
        **A. Signup/Registration Error Scenarios - Switch to Login:**
        If the 'after' image shows error messages indicating that an email is already in use, username already exists, account already exists, or similar messages (in any language including German), suggest switching to login instead of continuing with registration/signup. Common error messages to watch for include:
        - "Email already in use" / "E-Mail bereits verwendet" / "E-Mail schon vorhanden"
        - "Username already exists" / "Benutzername bereits vorhanden" / "Nutzername bereits vergeben"
        - "Account already exists" / "Konto bereits vorhanden" / "Benutzer bereits registriert"
        - "Diese E-Mail-Adresse ist bereits registriert" / "This email is already registered"
        - "User already exists" / "Benutzer existiert bereits"
        - Any similar variations indicating the account is already registered
        When such messages are detected, recommend: "Switch to login process instead of continuing registration, as the account already exists."
        
        **B. Login Error Scenarios - Switch to Registration:**
        If the 'after' image shows error messages indicating that no account exists, wrong credentials, or login failure (in any language including German), suggest switching to registration/signup instead of continuing with login attempts. Common error messages to watch for include:
        - "No account found" / "Kein Konto gefunden" / "Benutzer nicht gefunden"
        - "Wrong username or password" / "Falscher Benutzername oder Passwort" / "Ungültige Anmeldedaten"
        - "Invalid credentials" / "Ungültige Zugangsdaten" / "Fehlerhafte Anmeldedaten"
        - "Login failed" / "Anmeldung fehlgeschlagen" / "Login fehlerhaft"
        - "User does not exist" / "Benutzer existiert nicht" / "Nutzer nicht vorhanden"
        - "Account not found" / "Konto nicht gefunden"
        - "Incorrect email or password" / "E-Mail oder Passwort falsch"
        - "Authentication failed" / "Authentifizierung fehlgeschlagen"
        - Any similar variations indicating the account doesn't exist or credentials are wrong
        When such messages are detected, recommend: "Switch to registration/signup process instead of continuing login attempts, as the account may not exist."
        
        **C. Critical Decision Logic:**
        - On SIGNUP pages with "account exists" errors → Suggest switching to LOGIN
        - On LOGIN pages with "account not found/wrong credentials" errors → Suggest switching to SIGNUP/REGISTRATION
        - Always quote the exact error message in the outcome_summary field
        - Do not suggest retrying the same action when these specific error types are detected
    
    6. **Reading and reporting new messages**
        Carefully examine the 'after' image for any new text, error, or success messages. If such a message is visible, quote it exactly in the outcome_summary field. If no new message is visible, state 'No new message detected.'
    
    7. **DO NOT MIND THE CAPTCHA SOLVING**
        Please be mindful of the "solving captcha" and "captcha solved" boxes that might appear randomly on the page; they simply mean that the extension that I have put to work on for solving captchas is doing its job. It is harmless and doesn't affect any other part of our agent's automation.
    ## Guidelines
    * Always respect the given JSON format.  
    * Simply because a current page is empty and needs to be filled with information, it does not mean that the step taken by action agent was incomplete; it can also mean that the page object just arrived here, as a direct cause of the previous action. You can take the previous page screenshot and action agent history as context to determine that easily.
    * Simply because a page CAN be scrolled down, it shouldn't be grounds for it to be scrolled down. If an action was taken successfully by the action agent and it is reflected in the before/after screenshots, scrolling is not necessary at all. Please refer to the overall webpage image that is also provided to you to help you determine this.
    * The next action that you suggest should be concise and precise. Easy to understand directions as to what needs to be done next. 
    * If you detect any anomaly or unexpected behavior (such as no visible change after an action, unexpected page state, repeated popups, etc.), describe it in the 'anomaly_detected' field. If no anomaly is detected, return an empty string or 'None'.
    * Always read and report any new error or success messages from the 'after' image in the outcome_summary field.
    * Always refer to the full webpage view image and cross reference it with the after image to accurately determine whether scrolling up/down is required or not.
    * Sometimes while filling out a lot of fields at once some might get left out; in the new after state if some elements are left out you must make sure they are filled.
    * PLEASE MAKE SURE TO CHECK ALL ACKNOWLEDGEMENT BOXES / I AGREE BOXES / I CONSENT BOXES and other similar check-boxes.
    * Only scroll if the current viewport (after-image) shows no unfilled inputs or unchecked boxes. Prioritize completing everything visible before initiating a scroll.
    * If you detect error messages indicating email/username already exists or account already registered, immediately suggest switching to login instead of continuing registration. Do not recommend trying different credentials for signup.
    * If you detect error messages indicating account not found, wrong credentials, or login failure, immediately suggest switching to registration/signup instead of continuing login attempts. Do not recommend retrying login with same credentials.
    * Always prioritize flow control decisions (login ↔ signup switching) over other suggestions when authentication errors are detected.
    
    ## FINAL CRITICAL CHECK BEFORE OUTPUT
    **BEFORE generating your response, ask yourself:**
    1. "Are there any unfilled form fields, empty text boxes, or unchecked required checkboxes visible in the after-image?"
    2. "Is the agent trying to submit/continue but no submit button is visible in the current view?"
    3. "Does the full webpage image show a submit/continue button that's not visible in the after-image?"
    4. "Are there any authentication error messages in the after-image?"
    5. "If on signup page: Does the error indicate account already exists? → Suggest switch to login"
    6. "If on login page: Does the error indicate account not found/wrong credentials? → Suggest switch to signup"
    
    **PRIORITY ORDER:**
    1. **If question 1 is true (unfilled elements exist), DO NOT scroll. Set scroll_up_down to -1 and suggest filling the visible elements first.**
    2. **If question 1 is false AND questions 2-3 are true (all visible elements are filled but submit button is missing), THEN set scroll_up_down to 2 (scroll down) to find the missing button.**
    3. **If questions 4-6 detect authentication errors, prioritize flow switching suggestions over other actions.**
    
    ## Strict JSON output wrapper
    You are to strictly follow the given json output format. Your output should contain nothing but the json formatted output, no headers no headings no footers and definitely no ```json``` tags. Pure, simple json starting and ending with curly brace.
    {
        action_verification : (If action taken by action agent was successful or not depending on your analysis of history and before/after screenshots) |bool|
        next_action_suggestion : (based on your intuition suggest what to do next) |string| ,
        scroll: (your analysis of whether the current page needs to be scrolled up/down or not) |string|  , 
        scroll_up_down : (if scrolling indeed is necessary then in which direction? -1 for scrolling not necessary, 1 for scrolling up and 2 for scrolling down) |int| 
        anomaly_detected : (describe any anomaly or unexpected behavior detected during the verification process, such as no visible change after an action, unexpected page state, repeated popups, or anything else unusual. If no anomaly is detected, return an empty string or 'None') |string|
        outcome_summary : (A brief summary of the outcome. If an error or success message is visible in the 'after' image, quote it here. Example: 'Login fehlerhaft! Bitte versuchen Sie es noch einmal...' or 'Registration successful.' If no new message is visible, state 'No new message detected.') |string|
    }
    """
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def vericomm_agent( image_path_1: str, image_path_2 : str , complete_site_image_path : str , action_history, current_action  ):
    ## 7 iteration k baad 1st wala delete krdo and so on
    with open(image_path_1, "rb") as f:
        b64_image = base64.b64encode(f.read()).decode("utf-8")
        data_uri_1 = f"data:image/jpeg;base64,{b64_image}"
    with open(image_path_2, "rb") as f:
        b64_image = base64.b64encode(f.read()).decode("utf-8")
        data_uri_2 = f"data:image/jpeg;base64,{b64_image}"
        
    with open(complete_site_image_path, "rb") as f:
        b64_image = base64.b64encode(f.read()).decode("utf-8")
        data_uri_scroll = f"data:image/jpeg;base64,{b64_image}"

    sys_message = [{"role": "system", "content": first_AGENT_PROMPT}] 
  
    action_history_text = str(action_history) 
 
    current_message = [
        {
            "role": "user",
            "content": [
                { "type": "text","text":f"""THE following is the action agent's history , a list of actions that have happened until now
                 
                 {action_history_text}
                 
                  You also need to keep in mind what action the agent just did that resulted in the change in screenshots presented to you , which is : {current_action} , in order to properly verify action""" },
                { "type": "text", "text": "This is the before image:" },
                { "type": "image_url", "image_url": { "url": data_uri_1} },
                { "type": "text", "text": "This is the after image, after the action took place:" },
                { "type": "image_url", "image_url": { "url": data_uri_2 } },
                { "type": "text" , "text": "The following image is a total overview of the entire webpage, cross reference this with the after-image and determine if scrolling is required or not. Your judgement should be better if you use this method of determination regarding scrolling"},
                { "type" : "image_url","image_url": {"url": data_uri_scroll}}
                
            ]
        }
    ]

    
    messages = list(chain(sys_message, current_message))

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        tools=tool_schema,
        tool_choice={"type": "function", "function": {"name": "verification-action"}}
    )

    # Extract structured JSON
    tool_output = response.choices[0].message.tool_calls[0].function.arguments
    return  json.loads(tool_output)