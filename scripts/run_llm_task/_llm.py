from __future__ import annotations

import sys

try:
    import openai
except ImportError:
    sys.exit("openai package not found. Run: pip install openai")

from _config import GITHUB_MODELS_URL


def build_client(token: str) -> openai.OpenAI:
    """Return an OpenAI client configured for GitHub Models."""
    return openai.OpenAI(base_url=GITHUB_MODELS_URL, api_key=token)


def call_llm(
    client: openai.OpenAI,
    model: str,
    system_prompt: str,
    source: str,
    task_name: str,
) -> str:
    """Send *source* to the model with *system_prompt* and return the result."""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Apply the task '{task_name}' to the following source file. "
                    "Return the complete file and nothing else — no code fences, "
                    "no commentary before or after.\n\n"
                    f"{source}"
                ),
            },
        ],
        temperature=0,
    )
    return response.choices[0].message.content or source
