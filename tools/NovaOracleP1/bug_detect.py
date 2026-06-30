from llm_interface import LLMInterface
import configparser
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
bounding boxes indicating user actions.

Your goal is to determine whether any non-crash functional bug exists in
this tested sequence.

  ------------------------------------------------------------
  ### [Bug Examples] The categories of bugs include: -
  Functional mismatch - Missing effect - Wrong navigation -
  State inconsistency - Input validation issue - Permission or
  logic error
  ------------------------------------------------------------
  ### [Commonsense CoT] Let’s think step by step.

  1. Expected Path: Based on the commonsense, predict what the
  expected exploration steps should look like. Describe the
  expected page transitions and expected UI changes.

  2. Actual Path: The tested function sequence is as follows:
  $pagepath

  Compare the expected path and the actual path step by step.
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
  test sequence based on: - The expected vs. actual path comparison.

  For each step: - Determine whether the page transition meets
  expectation. - Identify any inconsistency or abnormal UI
  behavior. - If a bug exists, clearly specify the bug page 
  and related action.

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
“meets_expectation”: true, “reason”: “…” } ], “bug_found”: true,
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


class BugDetectInterface:
    def __init__(self):
        self.prompt = prompt
        self.LLM_interface = LLMInterface(api_key, model_name, url, temperature=0)

    def get_output(self, image):
        output, token_usage, prompt_tokens, completion_tokens = self.LLM_interface.get_response_from_lm(
            [image],
            self.prompt,
            return_json=True,
        )
        return output, token_usage, prompt_tokens, completion_tokens
