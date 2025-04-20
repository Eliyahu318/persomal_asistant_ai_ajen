import os
import re
from openai import OpenAI
from openai.types.chat import ChatCompletion


DEBUG_MODE = True

# Set your OpenAI API key
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI()


def clean_gpt_response(text_response: str) -> str:
    text_response = re.sub(r"^```(json)?\n?", "", text_response)
    text_response = re.sub(r"\n?```$", "", text_response)
    return text_response


def ask_gpt(system_prompt: str, user_input: str, model="gpt-4o", temperature=0.3) -> str:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input},
    ]
    response: ChatCompletion = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature
    )
    return clean_gpt_response(response.choices[0].message.content.strip())
