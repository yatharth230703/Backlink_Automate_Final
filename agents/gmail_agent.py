import os, pickle, re
from email import message_from_bytes
from base64 import urlsafe_b64decode
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from openai import OpenAI
import json
from dotenv import load_dotenv

load_dotenv()

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def extract_first_url(text: str) -> str | None:
    pattern = r'https?://\S+|www\.\S+'
    m = re.search(pattern, text)
    return m.group().rstrip('.,);:') if m else None

async def authenticate():
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as f:
            creds = pickle.load(f)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open('token.pickle', 'wb') as f:
            pickle.dump(creds, f)
    return creds

async def get_latest_full_body(service):
    resp = service.users().messages().list(userId='me', maxResults=1, labelIds=['INBOX']).execute()
    msgs = resp.get('messages', [])
    if not msgs:
        return None
    msg = service.users().messages().get(userId='me', id=msgs[0]['id'], format='raw').execute()
    raw = msg.get('raw', '')
    email_msg = message_from_bytes(urlsafe_b64decode(raw.encode('utf-8')))  # raw decode

    def walk_parts(msg):
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype == 'text/plain':
                    return part.get_payload(decode=True).decode('utf-8', errors='ignore')
        else:
            return msg.get_payload(decode=True).decode('utf-8', errors='ignore')
        return None

    return walk_parts(email_msg)

async def fetch_mail_url():
    creds = await authenticate()
    service = build('gmail', 'v1', credentials=creds)
    body = await get_latest_full_body(service)
    if not body:
        print("No email body found.")
        return None, None
    url = extract_first_url(body)
    print(type(url))
    print(url)
    return url, body



tool_schema = [
    {
        "type": "function",
        "function": {
            "name": "compare_content",
            "description": "Compare website homepage text and email body to determine if the email is related and contextually valid based on the website content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "related": {
                        "type": "boolean",
                        "description": "True if the email is contextually related to the website content, false otherwise."
                    }
                },
                "required": ["related"]
            }
        }
    }
]

email_analysis_schema = [
    {
        "type": "function",
        "function": {
            "name": "analyze_email_content",
            "description": "Analyze email content and provide specific instructions for the login agent on how to proceed with verification.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action_type": {
                        "type": "string",
                        "enum": ["navigate_url", "fill_otp", "both_available", "no_action"],
                        "description": "Type of action to take based on email content"
                    },
                    "verification_url": {
                        "type": "string",
                        "description": "Complete verification URL if found in email (only when action_type includes URL)"
                    },
                    "otp_code": {
                        "type": "string",
                        "description": "OTP/verification code if found in email (only when action_type includes OTP)"
                    },
                    "instructions": {
                        "type": "string",
                        "description": "Specific instructions for the login agent on what to do next"
                    },
                    "is_verification_email": {
                        "type": "boolean",
                        "description": "True if this appears to be a verification/signup related email"
                    },
                    "priority_action": {
                        "type": "string",
                        "enum": ["url", "otp", "none"],
                        "description": "Which action to prioritize if both URL and OTP are available"
                    }
                },
                "required": ["action_type", "instructions", "is_verification_email"]
            }
        }
    }
]

COMPARISON_PROMPT = """
You are a high-precision text analysis agent. Your task is to compare two bodies of text: one from a website's homepage and one from an email. Determine if the email body is related to and contextually valid given the website content. Return the result as a JSON object using the function schema provided. You must only return the boolean field 'related'.
"""

EMAIL_ANALYSIS_PROMPT = """
You are an email analysis agent specialized in extracting actionable instructions from verification emails. Your job is to analyze email content and provide specific instructions to a login automation agent.

Analyze the email content and determine what action should be taken:
1. If there's a verification URL - provide navigation instructions
2. If there's an OTP/verification code - provide the code to fill
3. If there's both - prioritize based on context
4. If it's not a verification email - indicate no action needed

Be very specific in your instructions. Examples:
- "Navigate to verification URL: https://example.com/verify?token=abc123"
- "Fill OTP code: 123456 in the verification field"
- "Email contains both URL and OTP - use OTP: 789012 for current page verification"
- "No verification content found in email"
"""

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def compare_agent(website_text: str, email_text: str):
    messages = [
        {"role": "system", "content": COMPARISON_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": f"Website Text:\n{website_text}"},
                {"type": "text", "text": f"Email Text:\n{email_text}"}
            ]
        }
    ]

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=tool_schema,
        tool_choice={"type": "function", "function": {"name": "compare_content"}}
    )

    tool_output = response.choices[0].message.tool_calls[0].function.arguments
    return json.loads(tool_output)

def email_analysis_agent(email_text: str, website_context: str = ""):
    """
    Analyze email content and provide specific instructions for login agent.
    
    Args:
        email_text: Full email content to analyze
        website_context: Optional context about the current website
    
    Returns:
        Dictionary with analysis results and instructions
    """
    context_info = f"Website context: {website_context}" if website_context else "No website context provided"
    
    messages = [
        {"role": "system", "content": EMAIL_ANALYSIS_PROMPT},
        {
            "role": "user",
            "content": f"""
Analyze this email content and provide instructions for the login automation agent:

{context_info}

Email Content:
{email_text}

Determine what action the login agent should take based on this email.
"""
        }
    ]

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=email_analysis_schema,
        tool_choice={"type": "function", "function": {"name": "analyze_email_content"}}
    )

    tool_output = response.choices[0].message.tool_calls[0].function.arguments
    result = json.loads(tool_output)
    
    print(f"📧 Email Analysis Result:")
    print(f"   Action Type: {result.get('action_type')}")
    print(f"   Is Verification Email: {result.get('is_verification_email')}")
    print(f"   Instructions: {result.get('instructions')}")
    if result.get('verification_url'):
        print(f"   Verification URL: {result.get('verification_url')}")
    if result.get('otp_code'):
        print(f"   OTP Code: {result.get('otp_code')}")
    
    return result

async def get_email_instructions(website_context: str = ""):
    """
    Fetch latest email and get AI-generated instructions for login agent.
    
    Args:
        website_context: Current website information for context
        
    Returns:
        Dictionary with email analysis and instructions, or None if no email
    """
    try:
        # Fetch latest email content
        creds = await authenticate()
        service = build('gmail', 'v1', credentials=creds)
        body = await get_latest_full_body(service)
        if not body:
            print("📧 No email found for analysis")
            return None
        
        # Analyze email with AI agent
        analysis = email_analysis_agent(body, website_context)
        
        # Add the full email text for reference
        analysis['full_email_text'] = body[:1000]  # First 1000 chars
        
        return analysis
        
    except Exception as e:
        print(f"❌ Error getting email instructions: {e}")
        return {"error": str(e), "action_type": "no_action", "is_verification_email": False, "instructions": "Email analysis failed"}
