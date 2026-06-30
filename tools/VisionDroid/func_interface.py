#Generate a function introduction for each step.
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
## Task
Please make a judgment based on the test sequence.
What is the function currently being tested?

## Test sequence of exploration steps (page descriptions + actions):
$actual_path

Return ONLY a JSON object in this exact format:
{
  "function_name": "...",
  "function_description": "...",
  "function_goal": "..."
}

Do not include any extra text, explanations, or formatting outside the JSON.
"""

class FuncInterface:
    def __init__(self):
        self.prompt = Template(prompt)
        self.LLM_interface = LLMInterface(api_key, model_name, url)

    def get_output(self,actual_path):
        prompt = self.prompt.substitute(actual_path = actual_path)
        output, token_usage, prompt_tokens, completion_tokens = self.LLM_interface.get_response_from_lm([], prompt, return_json=True)
        return output, token_usage, prompt_tokens, completion_tokens
