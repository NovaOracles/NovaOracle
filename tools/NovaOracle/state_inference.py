from llm_interface import LLMInterface
from string import Template
import configparser
import json
import os


config = configparser.ConfigParser()
config.read(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.ini'))
api_key = config.get('S', 'api_key')
model_name = config.get('S', 'model_name')
url = config.get('S', 'url')

prompt = """
## Role
You are an expert Android App tester specializing in analyzing GUI-based state changes.

## Input
You are given:
1. A concatenated screenshot strip arranged from left to right. Each image represents a sequential page step.
2. Annotated red bounding boxes indicating user actions.
3. A test sequence of exploration steps (page descriptions + actions):
$exploration_steps
4. View hierarchy diffs between adjacent page steps:
$xml_diffs

Each view hierarchy diff contains semantic attribute updates of matched UI nodes from step N to step N+1.

## Task
Let's think step by step.
Identify ONLY persistent state changes, such as changes to app data, user/account state, granted permissions, saved preferences, or system settings.
Do NOT include transient UI changes, such as page/directory navigation, scrolling, focus changes, menus, dialogs, toast messages, or unsaved text input.

For each state change:
1. Identify the adjacent transition where the state changes, using `from_page` and `to_page`.
2. Determine the persistent state variable and its value before and after the transition.
3. Describe the state change in one concise sentence.
4. Provide concise evidence using either screenshot evidence or view hierarchy diff evidence.

## OUTPUT FORMAT (STRICT JSON)
Return ONLY a JSON object in the following format. Do NOT include markdown formatting (like ```json) or extra explanations outside the JSON object.
{
  "state_changes": [
    {
      "from_page": 2,
      "to_page": 3,
      "state_variable": "...",
      "before_value": "...",
      "after_value": "...",
      "change_description": "...",
      "evidence": "..."
    }
  ]
}

## Rules
- You must use both textual descriptions and visual evidence from screenshots to reason.
- Do not hallucinate widgets not shown in the legend or steps.
- If no persistent state change is found, return {"state_changes": []}.
- Keep reasoning concise but logically grounded in provided evidence.
"""


def prompt_value(value):
    if isinstance(value, str):
        return value

    return json.dumps(value, ensure_ascii=False, indent=2)


class StateInferenceInterface:
    def __init__(self):
        self.prompt = Template(prompt)
        self.LLM_interface = LLMInterface(api_key, model_name, url, temperature=0)

    def build_prompt(self, exploration_steps, xml_diffs):
        return self.prompt.substitute(
            exploration_steps=prompt_value(exploration_steps),
            xml_diffs=prompt_value(xml_diffs),
        )

    def get_output(self, image, exploration_steps, xml_diffs):
        prompt = self.build_prompt(exploration_steps, xml_diffs)
        output, token_usage, prompt_tokens, completion_tokens = self.LLM_interface.get_response_from_lm(
            [image],
            prompt,
            return_json=True,
        )
        return output, token_usage, prompt_tokens, completion_tokens
