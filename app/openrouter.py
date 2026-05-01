"""
Octo Agent — LLM Client
========================
Generalized OpenAI-compatible API client. Works with OpenRouter, OpenAI,
Ollama, LM Studio, Together AI, Groq, or any OpenAI-compatible endpoint.
"""
import os
from pathlib import Path
from typing import Any, Dict, List

import requests


class OpenRouterClient:
    """OpenAI-compatible chat client for any API endpoint."""

    DEFAULT_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini", endpoint: str | None = None, timeout: int = 120):
        self.api_key = api_key.strip()
        self.model = model
        self.endpoint = (
            endpoint
            or os.getenv("OPENAI_API_BASE")
            or os.getenv("OPENROUTER_API_BASE")
            or self.DEFAULT_ENDPOINT
        )
        self.timeout = timeout
        # Ensure endpoint ends with /chat/completions if it looks like a base URL
        if self.endpoint.rstrip("/").endswith("/v1") or self.endpoint.rstrip("/").endswith("/api"):
            self.endpoint = self.endpoint.rstrip("/") + "/chat/completions"

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "OctoAgent/2.0 python-requests",
        }

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 1200) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            response = requests.post(self.endpoint, json=payload, headers=self._headers(), timeout=self.timeout)
        except requests.exceptions.RequestException as exc:
            error_text = str(exc)
            if "getaddrinfo failed" in error_text or "NameResolutionError" in error_text:
                raise RuntimeError(
                    "DNS resolution failed. "
                    "Verify your network DNS and that the endpoint host resolves. "
                    f"Endpoint: {self.endpoint}. Error: {error_text}") from exc
            raise RuntimeError(
                "Connection error. Verify your network, proxy settings, and API endpoint. "
                f"Endpoint: {self.endpoint}. Error: {error_text}") from exc

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(
                f"HTTP error {response.status_code}: {response.text.strip() or exc}") from exc

        content_type = response.headers.get("Content-Type", "")
        if response.text.lstrip().startswith("<") or "text/html" in content_type:
            raise RuntimeError(
                "Received HTML instead of API JSON. "
                "This usually means the endpoint is incorrect. "
                f"Endpoint: {self.endpoint}. Response: {response.text.strip()[:400]!r}")

        try:
            data = response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"Non-JSON response: {response.status_code} {response.text.strip()!r}. "
                f"Endpoint: {self.endpoint}") from exc

        if "choices" in data and len(data["choices"]) > 0:
            return data["choices"][0].get("message", {}).get("content", "").strip()

        raise RuntimeError(f"Unexpected response: {data}")

    def chat_with_tools(
        self,
        messages: List[Dict],
        tools: List[Dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        """Send a chat request with tool definitions. Returns the full assistant message dict."""
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools

        try:
            response = requests.post(self.endpoint, json=payload, headers=self._headers(), timeout=self.timeout)
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f"Connection error: {exc}") from exc

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(
                f"HTTP error {response.status_code}: {response.text.strip()[:500] or exc}"
            ) from exc

        content_type = response.headers.get("Content-Type", "")
        if response.text.lstrip().startswith("<") or "text/html" in content_type:
            raise RuntimeError("Received HTML instead of JSON. Check your endpoint and API key.")

        try:
            data = response.json()
        except ValueError as exc:
            raise RuntimeError(f"Non-JSON response: {response.text[:300]!r}") from exc

        if "choices" in data and len(data["choices"]) > 0:
            return data["choices"][0].get("message", {})

        raise RuntimeError(f"Unexpected response: {data}")

    def get_models(self) -> List[Dict[str, Any]]:
        models_endpoint = self.endpoint.replace("/chat/completions", "/models")
        try:
            response = requests.get(
                models_endpoint,
                headers=self._headers(),
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json().get("data", [])
        except Exception as exc:
            raise RuntimeError(f"Failed to fetch models: {exc}") from exc
