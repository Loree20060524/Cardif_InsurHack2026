"""Select the configured model provider without changing application contracts."""

from ..config import AI_PROVIDER
from .groq import call_groq_structured_json
from .ollama import call_ollama_structured_json


def call_structured_json(*, instructions, input_text, schema, context_window=None, local_only=False, think=None):
    if AI_PROVIDER == "groq":
        if local_only:
            raise RuntimeError("此分析僅允許本機模型，不能傳送到 Groq。")
        return call_groq_structured_json(instructions=instructions, input_text=input_text, schema=schema)
    return call_ollama_structured_json(
        instructions=instructions, input_text=input_text, schema=schema,
        context_window=context_window, local_only=local_only, think=think,
    )
