import os
import base64
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

LOGIN_STATUS_PROMPT = """
You are a high-precision web page analysis agent. Your task is to analyze both a webpage screenshot and its HTML content to determine if the user appears to be logged into their account.

Look for indicators such as:
- User profile/account sections
- Logout buttons or options
- Dashboard elements
- Personalized content
- "Mein Konto", "Profil", "Abmelden" (German for account, profile, logout)
- User avatar or name displayed
- Account management options
- Any indication that shows the user has access to logged-in features

Do NOT consider the following as logged-in indicators:
- Login/signup forms or buttons
- Registration prompts
- Cookie acceptance banners
- General website navigation

Return the result as a JSON object using the function schema provided. You must return the boolean field 'logged_in', confidence level, and reasoning.
"""

tool_schema = [
    {
        "type": "function",
        "function": {
            "name": "analyze_login_status",
            "description": "Analyze webpage screenshot and HTML content to determine if the user is logged in.",
            "parameters": {
                "type": "object",
                "properties": {
                    "logged_in": {
                        "type": "boolean",
                        "description": "True if the user appears to be logged in, false otherwise."
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
                "required": ["logged_in", "confidence", "reasoning"]
            }
        }
    }
]

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def check_login_status_with_ai(page) -> bool:
    """
    Use OpenAI to analyze a screenshot and page content to determine if the user is logged in.
    
    Args:
        page: The Playwright page object
        
    Returns:
        bool: True if user appears to be logged in, False otherwise
    """
    try:
        # Take a screenshot
        screenshot_path = "temp_login_check.png"
        await page.screenshot(path=screenshot_path, full_page=False)
        
        # Get page content
        page_content = await page.content()
        
        # Encode image to base64
        with open(screenshot_path, "rb") as f:
            b64_image = base64.b64encode(f.read()).decode("utf-8")
            data_uri = f"data:image/png;base64,{b64_image}"
        
        # Prepare messages for the API call
        messages = [
            {"role": "system", "content": LOGIN_STATUS_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Screenshot Analysis:\nPlease analyze the attached screenshot for login indicators."},
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
            tool_choice={"type": "function", "function": {"name": "analyze_login_status"}},
            max_tokens=300,
            temperature=0.1
        )
        
        # Parse the response from function call
        tool_output = response.choices[0].message.tool_calls[0].function.arguments
        result = json.loads(tool_output)
        
        print(f"🔍 Login Status Check - Logged in: {result['logged_in']}, Confidence: {result['confidence']}")
        print(f"📝 Reasoning: {result['reasoning']}")
        
        # Clean up temporary file
        try:
            os.remove(screenshot_path)
        except:
            pass
            
        return result['logged_in']
        
    except Exception as e:
        print(f"⚠️ Error checking login status with AI: {e}")
        # Fallback to basic URL check
        current_url = page.url.lower()
        return any(indicator in current_url for indicator in ['dashboard', 'profile', 'account', 'user'])
