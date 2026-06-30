from llm_interface import LLMInterface
from string import Template
import configparser
config = configparser.ConfigParser()
config.read('config.ini')
api_key = config.get('S', 'api_key')
model_name = config.get('S', 'model_name')
url = config.get('S', 'url')

prompt = """
### Task Instruction
Analyze the provided screenshot of a mobile application interface and generate a **brief, factual page description** (1-2 sentences maximum).

### Key Requirements
1. Focus on core elements:
   - Main function/purpose of the page (e.g., file manager, search results, settings)
   - Key UI components visible (e.g., navigation bar, buttons, text fields, lists)
   - Critical contextual information (e.g., current path, file count, active tab)
2. Be concise: Avoid unnecessary details (e.g., exact pixel positions, color shades)
3. Be objective: Only describe what is visually present (no assumptions or interpretations)
4. Use simple, clear language (suitable for technical analysis)

### Example Outputs
- "File manager interface showing the /storage/emulated/0/Download directory with 1 file (123.txt) and standard navigation/action buttons."
- "Settings page for a mobile app with toggle switches for notifications, privacy, and account preferences, plus a back button in the top-left corner."

### Output Format
Return ONLY the page description (no extra explanations, bullet points, or formatting).
"""

class PageDescriptionGen:
    def __init__(self):
        self.prompt = Template(prompt)
        self.LLM_interface = LLMInterface(api_key, model_name, url, temperature = 0)

    def get_output(self,image):
        output, token_usage, prompt_tokens, completion_tokens = self.LLM_interface.get_response_from_lm([image], prompt)
        return output, token_usage, prompt_tokens, completion_tokens