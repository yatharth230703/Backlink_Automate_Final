import os
import base64
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

REGISTRATION_STATUS_PROMPT = """
You are a high-precision web page analysis agent. Your task is to analyze both a webpage screenshot and its HTML content to determine if a business registration process has been completed successfully.

Look for indicators such as:
- Success messages or confirmation pages
- "Registration successful", "Account created", "Welcome" messages
- "Registrierung erfolgreich", "Konto erstellt", "Willkommen" (German equivalents)
- Business listing confirmation pages
- Account activation messages
- Email verification confirmations
- Dashboard or account management pages that indicate successful registration
- Business profile pages showing the registered business
- Messages indicating the business is now listed/registered
- Thank you pages after successful registration
- Pages showing business details or listing status

Do NOT consider the following as registration completion indicators:
- Registration forms or signup pages
- Verification emails pending (unless clearly stating registration is complete)
- Loading or processing pages
- Error messages
- Login pages
- General website navigation
- Cookie acceptance banners
- Captcha pages

Return the result as a JSON object using the function schema provided. You must return the boolean field 'registration_complete', confidence level, and reasoning.
"""

tool_schema = [
    {
        "type": "function",
        "function": {
            "name": "analyze_registration_status",
            "description": "Analyze webpage screenshot and HTML content to determine if business registration is complete.",
            "parameters": {
                "type": "object",
                "properties": {
                    "registration_complete": {
                        "type": "boolean",
                        "description": "True if the business registration appears to be complete, false otherwise."
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "description": "Confidence level of the analysis."
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Brief explanation of the analysis and decision."
                    }
                },
                "required": ["registration_complete", "confidence", "reasoning"]
            }
        }
    }
]

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def check_registration_status_with_ai(page) -> bool:
    """
    Use OpenAI to analyze a screenshot and page content to determine if business registration is complete.
    
    Args:
        page: The Playwright page object
        
    Returns:
        bool: True if registration appears to be complete, False otherwise
    """
    try:
        # Take a screenshot
        screenshot_path = "temp_registration_check.png"
        await page.screenshot(path=screenshot_path, full_page=False)
        
        # Get page content
        page_content = await page.content()
        
        # Encode image to base64
        with open(screenshot_path, "rb") as f:
            b64_image = base64.b64encode(f.read()).decode("utf-8")
            data_uri = f"data:image/png;base64,{b64_image}"
        
        # Prepare messages for the API call
        messages = [
            {"role": "system", "content": REGISTRATION_STATUS_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Screenshot Analysis:\nPlease analyze the attached screenshot for business registration completion indicators."},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                    {"type": "text", "text": f"HTML Content Analysis:\n{page_content[:3000]}..."}  # Limit content to avoid token limits
                ]
            }
        ]

        # Make the API call using function calling
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=tool_schema,
            tool_choice={"type": "function", "function": {"name": "analyze_registration_status"}},
            max_tokens=300,
            temperature=0.1
        )
        
        # Parse the response from function call
        tool_output = response.choices[0].message.tool_calls[0].function.arguments
        result = json.loads(tool_output)
        
        print(f"🔍 Registration Status Check - Complete: {result['registration_complete']}, Confidence: {result['confidence']}")
        print(f"📝 Reasoning: {result['reasoning']}")
        
        # Clean up temporary file
        try:
            os.remove(screenshot_path)
        except:
            pass
            
        return result['registration_complete']
        
    except Exception as e:
        print(f"⚠️ Error checking registration status with AI: {e}")
        # Fallback to basic URL/content check
        current_url = page.url.lower()
        page_text = await page.text_content('body')
        if page_text:
            page_text = page_text.lower()
            success_indicators = [
                'registration successful', 'account created', 'welcome',
                'registrierung erfolgreich', 'konto erstellt', 'willkommen',
                'business listed', 'listing created', 'thank you',
                'confirmation', 'success'
            ]
            return any(indicator in page_text for indicator in success_indicators)
        return False
