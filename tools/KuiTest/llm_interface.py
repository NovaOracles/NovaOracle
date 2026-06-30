import base64
import requests
import os
from time import sleep
from PIL import Image
import io

class LLMInterface:
    def __init__(self, api_key, model, url, temperature = 0, timeout = 180, max_retries = 5):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
        self.max_retries = max_retries
        self.url = url

    @staticmethod
    def encode_image(image_path: str) -> str:
        try:
            with Image.open(image_path) as img:
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                img.thumbnail((1080, 1080))
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=80)
                return base64.b64encode(buffer.getvalue()).decode('utf-8')
        except FileNotFoundError:
            raise FileNotFoundError(f"Image not found:: {image_path}")
        except Exception as e:
            raise RuntimeError(f"Image encoding failed: {str(e)}") from e


    def get_response_from_lm(self, images, prompt, return_json = False):
            content = []
            content.append({
                "type": "text",
                "text": prompt
            })
            api_key = self.api_key

            for i, image in enumerate(images):
                base64_image = self.encode_image(image)
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}"
                    }
                })

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "Cache-Control": "no-cache",
            }

            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": content
                    }
                ],
                "temperature": self.temperature,
            }
            if return_json:
                payload["response_format"] = {"type": "json_object"}

            retry_count = 0
            while retry_count < self.max_retries:
                try:
                    response = requests.post(
                        url=self.url,
                        headers=headers,
                        json=payload,
                        timeout=self.timeout
                    )

                    if response.status_code != 200:
                        print(f"API Error: Status {response.status_code}, Response: {response.text}")
                        if response.status_code in [400, 401, 403, 404]:
                            raise RuntimeError(f"API Client Error {response.status_code}: {response.text}")
                        response.raise_for_status()

                    response_data = response.json()
                    if 'choices' not in response_data or len(response_data['choices']) == 0:
                        raise RuntimeError(f"Empty choices in response: {response_data}")

                    outputs = response_data['choices'][0]['message']['content'].strip()
                    token_usage = response_data['usage']['total_tokens']
                    prompt_tokens = response_data['usage']['prompt_tokens']
                    completion_tokens = response_data['usage']['completion_tokens']
                    return outputs, token_usage, prompt_tokens, completion_tokens

                except requests.exceptions.Timeout:
                    retry_count += 1
                    wait_time = min(60, 10 * (2 ** retry_count))
                    print(f"[Timeout] Request timed out after {self.timeout}s. Retrying in {wait_time}s...")
                    sleep(wait_time)

                except requests.exceptions.RequestException as e:
                    retry_count += 1
                    status_code = getattr(getattr(e, 'response', None), 'status_code', None)

                    if status_code == 429:
                        wait_time = 20 * (2 ** retry_count)
                        print(f"[Rate Limit] 429 Too Many Requests. Retrying in {wait_time}s...")
                    else:
                        wait_time = 5 * (2 ** retry_count)
                        print(f"[Network Error] {str(e)}. Retrying in {wait_time}s...")

                    if retry_count >= self.max_retries:
                        break
                    sleep(wait_time)

                except KeyError as e:
                    resp_text = "No response object"
                    if 'response' in locals() and hasattr(response, 'text'):
                        resp_text = response.text
                    raise RuntimeError(f"Response format error. Missing key: {e}. Raw response: {resp_text}")

                except Exception as e:
                    print(f"Unexpected error: {e}")
                    retry_count += 1
                    if retry_count >= self.max_retries:
                        break
                    sleep(5)

            raise TimeoutError(f"Failed after {self.max_retries} retries. Last error was Timeout or Network issue.")