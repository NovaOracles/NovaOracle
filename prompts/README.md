## 1. State Inference               

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

------

## 2. Bug Detection

    Detector Prompt Template
    
    Below are instructions for the no-crash bug detection task.
    
    [Task Description]
    You are given:
    1. A sequence of exploration steps (page descriptions + actions).
    3. A concatenated screenshot strip arranged from left to right and top to bottom.
    4. Annotated colored bounding boxes indicating user actions.
    5. Persistent state changes inferred from the execution history.
    
    Your goal is to determine whether any non-crash functional bug exists in this tested sequence.
    
    ------------------------------------------------------------
    ### [Bug Examples]
    The categories of bugs include:
    - Functional mismatch
    - Missing effect
    - Wrong navigation
    - State inconsistency
    - Input validation issue
    - Permission or logic error
    ------------------------------------------------------------
    ### [State-Behavior Consistency Checking]
    Let’s think step by step.
    
    1. Expected Path:
    Based on the commonsense, predict what the expected exploration steps should look like. Describe the expected page transitions and expected UI changes.
    
    2. Actual Path:
    The tested function sequence is as follows:
    $pagepath
    
    Compare the expected path and the actual path step by step.
    In addition to checking page transitions and UI changes, independently check whether the GUI behavior at each step is consistent with all persistent states inferred from earlier interactions.
    
    3. Persistent State Changes:
    The persistent state changes inferred by the execution history are as follows:
    $statechanges
    
    For each persistent state change, identify the subsequent steps whose behavior should be affected by that state.
    Check whether any subsequent GUI behavior contradicts the the persistent states.
    
    A page transition and UI change may appear normal when compared with the immediately preceding step but still exist a bug if its behavior conflicts with the previously inferred persistent states in the execution history.
    ------------------------------------------------------------
    
    [Legend of Image]
    
    The screenshot strip shows the test sequence arranged in order from left to right and from top to bottom.
    
    Each screenshot contains colored bounding boxes indicating the user operation:
    - Red box: click, input, long click
    Each bounding box corresponds to a specific action in the step sequence.
    
    You must use both textual descriptions and visual evidence from screenshots to reason.
    
    ------------------------------------------------------------
    ### [Query]
    
    (1) Querying Bug Detection:
    Please analyze each step in the test sequence based on:
    - The expected vs. actual path comparison,
    - The persistent states inferred from the execution history.
    
    For each step:
    - Determine whether the page transition meets expectation.
    - Identify any inconsistency or abnormal UI behavior.
    - Determine whether the observed behavior is consistent with the persistent states.
    - Identify any inconsistency between the observed behavior and the persistent states.
    - If a bug exists, clearly specify the bug page and related action.
    
    If any step has: "meets_expectation": false, or "state_behavior_consistency": false, then "bug_found" SHOULD be true.
    
    (2) Querying Possible Bug Path:
    Is there any page or operation in the current path that could potentially trigger bugs? If yes, provide:
    - The corresponding page
    - The specific action widget
    - The reasoning
    
    (3) Querying Exception Path:
    By analyzing the test path:
    - Are there any abnormal, redundant, or logically inconsistent operations?
    - Provide the corresponding page and action widget.
    ------------------------------------------------------------
    
    OUTPUT FORMAT (STRICT JSON)
    
    Return ONLY a JSON object in the following format:
    
    {
      "function_name": "...",
      "expected_path_summary": "...",
      "step_analysis": [
        {
          "step_id": 1,
          "expected_behavior": "...",
          "actual_behavior": "...",
          "meets_expectation": true,
          "state_behavior_consistency": true,
          "reason": "..."
        }
      ],
      "bug_found": true,
      "bug_page_step": 4,
      "bug_type": "functional_mismatch | missing_effect | wrong_navigation | state_inconsistency | input_validation | other | none",
      "bug_description": "...",
      "possible_bug_paths": [
        {
          "page_step": 3,
          "action_widget": "...",
          "risk_reason": "..."
        }
      ],
      "exception_paths": [
        {
          "page_step": 2,
          "action_widget": "...",
          "abnormal_reason": "..."
        }
      ],
      "confidence": 0.0
    }
    
    Rules:
    - Do not hallucinate widgets not shown in the legend or steps.
    - If no bug is found, set "bug_found": false and "bug_type": "none".
    - Keep reasoning concise but logically grounded in provided evidence.