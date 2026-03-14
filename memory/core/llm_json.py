"""Shared helpers for structured JSON chat-completion calls."""

import json
from typing import Type

from pydantic import BaseModel


def call_llm_with_json(chat_client, model: str, system_prompt: str, user_prompt: str, output_model: Type[BaseModel]) -> BaseModel:
    """Call a chat-completions client and validate the JSON response."""
    schema_hint = f"\nRespond with valid JSON matching this schema: {output_model.model_json_schema()}"

    response = chat_client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt + schema_hint},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )

    content = response.choices[0].message.content
    parsed = json.loads(content)
    return output_model.model_validate(parsed)
