from openai import OpenAI
import base64
import json
from dotenv import load_dotenv
from itertools import chain 
from abc import ABC, abstractmethod
import os

load_dotenv()

class BaseAgent(ABC):
    """Base class for automation agents with shared functionality."""
    
    def __init__(self, api_key: str = None, business_data_file: str = "business_data.json"):
        """
        Initialize the base agent.
        
        Args:
            api_key: OpenAI API key. If None, will use environment variable.
            business_data_file: Path to business data JSON file.
        """
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self.business_data = self._load_business_data(business_data_file)
        
    def _load_business_data(self, file_path: str) -> dict:
        """Load business data from a JSON file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Business data file '{file_path}' not found")
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON format in '{file_path}'")
    
    @abstractmethod
    def get_tool_schema(self) -> list:
        """Return the tool schema specific to this agent type."""
        pass
    
    @abstractmethod
    def get_agent_prompt(self) -> str:
        """Return the system prompt specific to this agent type."""
        pass
    
    def _encode_image(self, image_path: str) -> str:
        """Encode image to base64 data URI."""
        with open(image_path, "rb") as f:
            b64_image = base64.b64encode(f.read()).decode("utf-8")
            return f"data:image/jpeg;base64,{b64_image}"
    
    def _prepare_messages(self, user_prompt: str, data_uri: str, message_history: list) -> list:
        """Prepare message list for OpenAI API call."""
        sys_message = [{"role": "system", "content": self.get_agent_prompt()}]
        
        current_message = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": data_uri}}
                ]
            }
        ]
        
        # If message length is more than 8, remove the first two messages
        if len(message_history) > 8:
            message_history = message_history[2:]
        
        return list(chain(sys_message, message_history, current_message))
    
    def execute(self, image_path: str, user_prompt: str, message_history: list, debug: bool = False, website_context: str = "") -> tuple:
        """
        Execute the agent with given inputs.
        
        Args:
            image_path: Path to the screenshot image
            user_prompt: User prompt with elements data
            message_history: Previous conversation history
            debug: Whether to print debug information
            website_context: Current website context for email analysis
            
        Returns:
            Tuple of (data_uri, agent_result)
        """
        # Encode image
        data_uri = self._encode_image(image_path)
        
        # Prepare messages
        messages = self._prepare_messages(user_prompt, data_uri, message_history)
        
        # Get tool schema
        tool_schema = self.get_tool_schema()
        
        # Make API call with auto tool choice to allow multiple tools
        response = self.client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=tool_schema,
            tool_choice="auto"
        )
        
        # Handle tool calls
        tool_calls = response.choices[0].message.tool_calls
        if not tool_calls:
            # Fallback to submit_directory_action if no tool calls
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                tools=tool_schema,
                tool_choice={"type": "function", "function": {"name": "submit_directory_action"}}
            )
            tool_calls = response.choices[0].message.tool_calls
        
        # Process tool calls
        main_result = None
        email_result = None
        
        for tool_call in tool_calls:
            if tool_call.function.name == "submit_directory_action":
                main_result = json.loads(tool_call.function.arguments)
            elif tool_call.function.name == "fetch_email_verification":
                email_args = json.loads(tool_call.function.arguments)
                email_result = self._handle_email_verification(email_args, website_context)
        
        # Use main result or first tool call result
        agent_result = main_result or json.loads(tool_calls[0].function.arguments)
        
        # Add email analysis if available
        if email_result:
            agent_result['email_analysis'] = email_result
        
        # Also check for check_email flag and fetch email if requested
        if agent_result.get('check_email') and not email_result:
            email_result = self._handle_email_verification({"content_type": "latest"}, website_context)
            if email_result:
                agent_result['email_analysis'] = email_result
        
        if debug:
            print("# =================== Agent Result (start) ===================")
            print(str(agent_result))
            if email_result:
                print("# =================== Email Analysis ===================")
                print(str(email_result))
            print("# =================== Agent Result (end) ===================")
        
        return data_uri, agent_result
    
    def _handle_email_verification(self, email_args: dict, website_context: str = "") -> dict:
        """Handle email verification tool call with AI analysis."""
        # Return a marker that email verification was requested
        # The actual async handling will be done in the login loop
        return {
            'email_verification_requested': True,
            'email_args': email_args,
            'website_context': website_context,
            'action_type': 'email_pending',
            'is_verification_email': True,
            'instructions': 'Email verification requested - will be processed in login loop'
        }
    
    def get_business_data_json(self) -> str:
        """Return business data as formatted JSON string for prompts."""
        return json.dumps(self.business_data, ensure_ascii=False, indent=4)
