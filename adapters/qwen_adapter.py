"""Local Qwen served by the existing llama.cpp launcher on port 8081."""

from openai import OpenAI

from .. import config
from .gemma_adapter import GemmaAdapter


class QwenAdapter(GemmaAdapter):
    PROVIDER = "qwen"

    def __init__(self, model: str = config.QWEN_MODEL):
        self.model = model
        self.client = OpenAI(
            api_key="local-llama-server-no-key-needed",
            base_url=config.QWEN_BASE_URL,
        )
