import asyncio
import json
import os
import re
import uuid

from dotenv import load_dotenv
from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta, StreamDone

load_dotenv()
API_KEY = os.environ["EMERGENT_LLM_KEY"]

MODELS = {
    "gpt-6-luna": {"provider": "openai", "model": "gpt-6-luna", "label": "GPT 6 Luna (OpenAI)"},
    "claude-sonnet-5-5": {"provider": "anthropic", "model": "claude-sonnet-5-5", "label": "Claude Sonnet 5.5 (Anthropic)"},
}
DEFAULT_MODEL = "gpt-6-luna"


def new_chat(model_key: str, system: str) -> LlmChat:
    spec = MODELS.get(model_key, MODELS[DEFAULT_MODEL])
    return LlmChat(api_key=API_KEY, session_id=str(uuid.uuid4()), system_message=system).with_model(
        spec["provider"], spec["model"]
    )


def send(chat: LlmChat, prompt: str) -> str:
    return asyncio.run(chat.send_message(UserMessage(text=prompt)))


def send_json(chat: LlmChat, prompt: str) -> dict:
    text = send(chat, prompt)
    try:
        return parse_json(text)
    except ValueError:
        fixed = send(chat, "Your previous reply was not valid JSON. Reply again with ONLY the JSON object, no prose.")
        return parse_json(fixed)


def parse_json(text: str) -> dict:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("LLM returned no JSON object")
    return json.loads(text[start : end + 1])


def stream(chat: LlmChat, prompt: str):
    """Sync generator bridging the async token stream."""
    agen = chat.stream_message(UserMessage(text=prompt))
    loop = asyncio.new_event_loop()
    try:
        while True:
            try:
                ev = loop.run_until_complete(agen.__anext__())
            except StopAsyncIteration:
                break
            if isinstance(ev, TextDelta):
                yield ev.content
            elif isinstance(ev, StreamDone):
                break
    finally:
        loop.close()
