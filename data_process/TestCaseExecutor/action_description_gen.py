from llm_interface import LLMInterface
import configparser
from string import Template
config = configparser.ConfigParser()
config.read("config.ini")
api_key = config.get('S', 'api_key')
model_name = config.get('S', 'model_name')
url = config.get('S', 'url')

prompt = """
You are an app tester. Based on the annotated screenshot and the Appium code, generate a concise description of the user operation.

## Rules
1.Use code to determine the operation type (tap, long press, swipe, send_keys, system key).
2.Use annotations to identify the target:
  - Red rectangle → the element inside the box.
  - Red circle + cross → the most visible text, button, or icon at the center. Never use vague terms like “near”.
  - Green circle → red line → red arrow circle → swipe. Direction = from green circle to arrow tip. If end Y > start Y = swipe down; end Y < start Y = swipe up.
3.Describe only the action, not the purpose:
  - Normal tap (pause 0.1s) → “Tap on [element]”.
  - Long press (pause after pointer_down) → “Long press on [element]”.
  - Send_keys → state the text before/after input as given in code comments.
  - System keys → “Press Back/Home/App Switch Button”.
  - If no annotation or other operation → describe directly from code.

## Operation Code
$operation_code

## Expected Output
Output only the operation description (no extra content, no explanation, no markdown).
"""

class ActionDescriptionGen:
    def __init__(self):
        self.prompt = Template(prompt)
        self.LLM_interface = LLMInterface(api_key, model_name, url, temperature = 0)

    def get_output(self, image, operation_code):
        prompt = self.prompt.substitute(operation_code = operation_code)
        output, token_usage, prompt_tokens, completion_tokens = self.LLM_interface.get_response_from_lm([image], prompt)
        return output, token_usage, prompt_tokens, completion_tokens