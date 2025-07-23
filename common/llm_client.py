import httpx
import json
import re
from typing import Dict, Any, List

from .settings import get_settings, LLMSettings

class LLMClient:
    """
    A client to interact with LLM APIs that are compatible with OpenAI's format,
    with support for different providers like OpenRouter.
    """
    def __init__(self, provider_name: str):
        settings = get_settings()
        
        provider_settings: LLMSettings = getattr(settings.llm_providers, provider_name, None)
        
        if not provider_settings:
            raise ValueError(f"LLM provider '{provider_name}' not found in settings.")

        self.api_key = provider_settings.api_key
        self.base_url = provider_settings.base_url
        self.provider_name = provider_name
        self.app_name = settings.app_name
        
        self.models = [model.strip() for model in provider_settings.models.split(',') if model.strip()]
        self.default_model = self.models[0] if self.models else None

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Calls the chat completion endpoint of the LLM.
        """
        if not self.api_key or not self.base_url:
            raise ValueError("API key and base URL must be configured for the provider.")
            
        model_to_use = model if model else self.default_model
        if not model_to_use:
            raise ValueError("No model specified and no default model configured.")

        api_url = f"{self.base_url.rstrip('/')}/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # Add OpenRouter specific headers if using that provider
        if self.provider_name == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/your-repo/social-media-content-generator" # Replace with your actual repo URL
            headers["X-Title"] = self.app_name

        payload = {
            "model": model_to_use,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(api_url, json=payload, headers=headers)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                print(f"HTTP error occurred: {e.response.status_code} - {e.response.text}")
                raise
            except httpx.RequestError as e:
                print(f"An error occurred while requesting {e.request.url!r}.")
                raise

def parse_llm_json_response(response_content: str) -> Dict[str, Any]:
    """
    Robustly parses a JSON object from a string that might contain extra text.
    It looks for a JSON block enclosed in ```json ... ``` or the first '{...}' block.
    """
    # First, try to find a ```json ... ``` block
    match = re.search(r"```json\s*(\{.*?\})\s*```", response_content, re.DOTALL)
    if match:
        json_str = match.group(1)
    else:
        # If not found, find the first '{' and the last '}'
        start_index = response_content.find('{')
        end_index = response_content.rfind('}')
        if start_index != -1 and end_index != -1 and end_index > start_index:
            json_str = response_content[start_index:end_index+1]
        else:
            raise json.JSONDecodeError("No valid JSON object found in the response.", response_content, 0)
    
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"Failed to decode JSON string: {json_str}")
        raise e

# Example Usage
async def main():
    # This requires settings to be configured with a valid provider.
    # Assuming 't8star_cn' is configured in settings.
    try:
        client = LLMClient(provider_name="t8star_cn")
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello! Can you tell me a joke?"}
        ]
        response = await client.chat_completion(messages)
        print(json.dumps(response, indent=2, ensure_ascii=False))
        
        # Accessing the content
        if response and "choices" in response and len(response["choices"]) > 0:
            content = response["choices"][0]["message"]["content"]
            print("\nAssistant's Joke:")
            print(content)

    except (ValueError, FileNotFoundError) as e:
        print(f"Configuration error: {e}")
        print("Please ensure your .env file and settings are correctly configured for the 't8star_cn' provider.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == '__main__':
    # This part is for demonstration and will likely fail if settings are not pre-configured.
    # To run this, you would need to have your .env file populated with
    # T8STAR_CN_API_KEY, T8STAR_CN_BASE_URL, and T8STAR_CN_MODELS
    import asyncio
    asyncio.run(main()) 