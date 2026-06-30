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
Here is a UI screenshot:

The component I selected is marked with a red bounding box in the image. The action description is: $action_description
Infer the function of the selected UI component based on the screenshot in one concise sentence.
Please ensure that your function predictions reflect high confidence.
"""

class FunctionIdentification:
    def __init__(self):
        self.llm_interface = LLMInterface(api_key, model_name, url, temperature = 0)
        self.prompt = Template(prompt)

    def func_identification(self, anno_image_path, action_description):
        prompt = self.prompt.substitute(action_description = action_description)
        output, token_usage, prompt_tokens, completion_tokens = self.llm_interface.get_response_from_lm([anno_image_path], prompt)
        return output, token_usage, prompt_tokens, completion_tokens
