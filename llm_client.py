from __future__ import annotations

import os
import time
from typing import Iterable, Optional

from log.custom_logger import log


class LLMClient:
    def __init__(
        self,
        model_name: str,
        *,
        openai_api_key: Optional[str] = None,
        google_api_key: Optional[str] = None,
        max_retries: int = 2,
        retry_sleep_seconds: float = 1.0,
    ):
        self.model_name = model_name
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self.google_api_key = google_api_key or os.getenv("GOOGLE_API_KEY")
        self.max_retries = max_retries
        self.retry_sleep_seconds = retry_sleep_seconds

    @property
    def provider(self) -> str:
        model = self.model_name.lower()
        if model == "mock":
            return "mock"
        if "gemini" in model:
            return "gemini"
        if "gpt" in model or model.startswith("o"):
            return "openai"
        return "openai"

    def ensure_ready(self) -> None:
        if self.provider == "mock":
            return
        if self.provider == "gemini" and not self.google_api_key:
            raise RuntimeError("GOOGLE_API_KEY is required for Gemini models.")
        if self.provider == "openai" and not self.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI models.")

    def complete(
        self,
        chat_history: Iterable[dict[str, str]],
        prompt: str,
        *,
        temperature: float = 1.0,
    ) -> str:
        if self.provider == "mock":
            return self._mock_response(prompt)

        for attempt in range(1, self.max_retries + 1):
            try:
                if self.provider == "gemini":
                    return self._complete_gemini(chat_history, prompt, temperature)
                return self._complete_openai(chat_history, prompt, temperature)
            except Exception as exc:
                log.logger.warning(
                    "%s api retry %s/%s: %s",
                    self.provider,
                    attempt,
                    self.max_retries,
                    exc,
                )
                if attempt < self.max_retries:
                    time.sleep(self.retry_sleep_seconds)

        log.logger.error("LLM API failed. Skipping this interaction.")
        return ""

    def _complete_openai(
        self,
        chat_history: Iterable[dict[str, str]],
        prompt: str,
        temperature: float,
    ) -> str:
        import openai

        client = openai.OpenAI(api_key=self.openai_api_key)
        messages = [
            {"role": message["role"], "content": message["content"]}
            for message in chat_history
        ]
        messages.append({"role": "user", "content": prompt})
        response = client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=temperature,
        )
        return response.choices[0].message.content or ""

    def _complete_gemini(
        self,
        chat_history: Iterable[dict[str, str]],
        prompt: str,
        temperature: float,
    ) -> str:
        import google.generativeai as genai

        genai.configure(api_key=self.google_api_key, transport="rest")
        generation_config = genai.types.GenerationConfig(
            candidate_count=1,
            temperature=temperature,
        )
        model = genai.GenerativeModel(self.model_name)
        contents = []
        for message in chat_history:
            role = "model" if message["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [message["content"]]})
        contents.append({"role": "user", "parts": [prompt]})
        response = model.generate_content(
            contents=contents,
            generation_config=generation_config,
        )
        return response.text or ""

    @staticmethod
    def _mock_response(prompt: str) -> str:
        normalized = prompt.lower()
        if "briefly post" in normalized:
            return "I will stay cautious and wait for clearer market signals."
        if "estimate whether you will buy" in normalized:
            return '{"buy_A":"no","buy_B":"no","sell_A":"no","sell_B":"no","loan":"no"}'
        if "whether to continue the loan" in normalized:
            return '{"loan":"no"}'
        if "whether to buy/sell" in normalized or "whether to buy or sell" in normalized:
            return '{"action_type":"no"}'
        return "{}"
