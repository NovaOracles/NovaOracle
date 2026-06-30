from llm_interface import LLMInterface
from string import Template
import configparser
import os

config = configparser.ConfigParser()
config.read(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.ini'))
api_key = config.get('S', 'api_key')
model_name = config.get('S', 'model_name')
url = config.get('S', 'url')

prompt = """
Here are the interacted component's function description, alone with the screenshot of the page after interaction:
$component_function

Determine whether the UI response after interaction aligns with the expectations?
Return ONLY a JSON object in the following format:
{
    "judgement": true/false,
    "reason": "Provide concise step-by-step reasoning",
    "confidence": 0.0 
}
"""

class ResponseVerification:
    def __init__(self):
        self.llm_interface = LLMInterface(api_key, model_name, url, temperature = 0)
        self.prompt = Template(prompt)

    def response_verification(self,image, component_function):
        prompt = self.prompt.substitute(component_function = component_function)
        output, token_usage, prompt_tokens, completion_tokens = self.llm_interface.get_response_from_lm([image], prompt, return_json=True)
        return output, token_usage, prompt_tokens, completion_tokens
