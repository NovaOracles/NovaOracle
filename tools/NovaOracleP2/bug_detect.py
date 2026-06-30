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
Detector Prompt Template

Below are instructions for the no-crash bug detection task.

[Task Description] You are given: 1. A sequence of exploration steps
(page descriptions + actions). 3. A concatenated screenshot strip
arranged from left to right and top to bottom. 4. Annotated colored
bounding boxes indicating user actions. 5. Persistent state changes
inferred from the execution history.

Your goal is to determine whether any non-crash functional bug exists in
this tested sequence.

  ------------------------------------------------------------
  ### [Bug Examples] The categories of bugs include: -
  Functional mismatch - Missing effect - Wrong navigation -
  State inconsistency - Input validation issue - Permission or
  logic error
  ------------------------------------------------------------
  ### [State-Behavior Consistency Checking] Let’s think step by step.

  1. Persistent State Changes: The persistent state changes
  inferred by the execution history are as follows:
  $statechanges

  For each persistent state change, identify the subsequent
  steps whose behavior should be affected by that state.
  Check whether any subsequent GUI behavior contradicts the
  the persistent states.

  A page transition and UI change may appear normal when compared with the
  immediately preceding step but still exist a bug if its
  behavior conflicts with the previously inferred persistent states
  in the execution history.
  ------------------------------------------------------------

[Legend of Image]

The screenshot strip shows the test sequence arranged in order from left
to right and from top to bottom.

Each screenshot contains colored bounding boxes indicating the user
operation: - Red box: click, input, long click
Each bounding box corresponds to a specific action in the step sequence.

You must use both textual descriptions and visual evidence from
screenshots to reason.

  ------------------------------------------------------------
  ### [Query]

  (1) Querying Bug Detection: Please analyze each step in the
  test sequence based on: - The persistent states inferred from
  the execution history.

  For each step: - Determine whether the observed behavior is
  consistent with the persistent states. - Identify any
  inconsistency between the observed behavior and the
  persistent states. - If a bug exists, clearly specify the
  bug page and related action.

  (2) Querying Possible Bug Path: Is there any page or
  operation in the current path that could potentially trigger
  bugs? If yes, provide: - The corresponding page - The
  specific action widget - The reasoning

  (3) Querying Exception Path: By analyzing the test path: -
  Are there any abnormal, redundant, or logically inconsistent
  operations? - Provide the corresponding page and action
  widget.
  ------------------------------------------------------------

OUTPUT FORMAT (STRICT JSON)

Return ONLY a JSON object in the following format:

{ “function_name”: “…”, “expected_path_summary”: “…”, “step_analysis”: [
{ “step_id”: 1, “expected_behavior”: “…”, “actual_behavior”: “…”,
“state_behavior_consistency”: true, “reason”: “…” } ], “bug_found”: true,
“bug_page_step”: 4, “bug_type”: “functional_mismatch | missing_effect |
wrong_navigation | state_inconsistency | input_validation | other |
none”, “bug_description”: “…”, “possible_bug_paths”: [ { “page_step”: 3,
“action_widget”: “…”, “risk_reason”: “…” } ], “exception_paths”: [ {
“page_step”: 2, “action_widget”: “…”, “abnormal_reason”: “…” } ],
“confidence”: 0.0 }

Rules: - Do not hallucinate widgets not shown in the legend or steps. -
If no bug is found, set “bug_found”: false and “bug_type”: “none”. -
Keep reasoning concise but logically grounded in provided evidence.
"""


def prompt_value(value):
    if isinstance(value, str):
        return value

    return json.dumps(value, ensure_ascii=False, indent=2)


class BugDetectInterface:
    def __init__(self):
        self.prompt = Template(prompt)
        self.LLM_interface = LLMInterface(api_key, model_name, url, temperature = 0)

    def get_output(self,image, pagepath, statechanges=None):
        prompt = self.prompt.substitute(
            pagepath = pagepath,
            statechanges = prompt_value(statechanges or {"state_changes": []}),
        )
        output, token_usage, prompt_tokens, completion_tokens = self.LLM_interface.get_response_from_lm([image],prompt,return_json=True)
        return output, token_usage, prompt_tokens, completion_tokens
