"""
LLM client utilities for idea_generator.
Supports: OpenAI, Anthropic (direct / Bedrock / Vertex AI), Ollama, Gemini, DeepSeek, Llama.
Adapted from AI Scientist v2's ai_scientist/llm.py – standalone, no external deps on ai_scientist.
"""

import json
import logging
import os
import re
from typing import Any

import anthropic
import backoff
import openai

logger = logging.getLogger(__name__)

MAX_NUM_TOKENS = 4096

AVAILABLE_LLMS = [
    # Anthropic Claude (direct)
    "claude-3-5-sonnet-20240620",
    "claude-3-5-sonnet-20241022",
    # OpenAI GPT
    "gpt-4o-mini",
    "gpt-4o-mini-2024-07-18",
    "gpt-4o",
    "gpt-4o-2024-05-13",
    "gpt-4o-2024-08-06",
    "gpt-4.1",
    "gpt-4.1-2025-04-14",
    "gpt-4.1-mini",
    "gpt-4.1-mini-2025-04-14",
    # GPT-5.2 (reasoning / thinking)
    "gpt-5.2",
    "gpt-5.2-2025-12-11",
    "gpt-5.2-pro",
    # OpenAI reasoning
    "o1",
    "o1-2024-12-17",
    "o1-preview-2024-09-12",
    "o1-mini",
    "o1-mini-2024-09-12",
    "o3-mini",
    "o3-mini-2025-01-31",
    # DeepSeek
    "deepseek-coder-v2-0724",
    "deepcoder-14b",
    # Llama
    "llama3.1-405b",
    # Bedrock Claude
    "bedrock/anthropic.claude-3-sonnet-20240229-v1:0",
    "bedrock/anthropic.claude-3-5-sonnet-20240620-v1:0",
    "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
    "bedrock/anthropic.claude-3-haiku-20240307-v1:0",
    "bedrock/anthropic.claude-3-opus-20240229-v1:0",
    # Vertex AI Claude
    "vertex_ai/claude-3-opus@20240229",
    "vertex_ai/claude-3-5-sonnet@20240620",
    "vertex_ai/claude-3-5-sonnet@20241022",
    "vertex_ai/claude-3-sonnet@20240229",
    "vertex_ai/claude-3-haiku@20240307",
    # Google Gemini
    "gemini-2.0-flash",
    "gemini-2.5-flash-preview-04-17",
    "gemini-2.5-pro-preview-03-25",
    # Ollama
    "ollama/gpt-oss:20b",
    "ollama/gpt-oss:120b",
    "ollama/qwen3:8b",
    "ollama/qwen3:32b",
    "ollama/qwen3:235b",
    "ollama/qwen2.5vl:8b",
    "ollama/qwen2.5vl:32b",
    "ollama/qwen3-coder:70b",
    "ollama/qwen3-coder:480b",
    "ollama/deepseek-r1:8b",
    "ollama/deepseek-r1:32b",
    "ollama/deepseek-r1:70b",
    "ollama/deepseek-r1:671b",
]


def create_client(model: str) -> tuple[Any, str]:
    """Create an LLM client for the given model identifier.
    Returns (client, resolved_model_name).
    """
    if model.startswith("claude-"):
        logger.info("Using Anthropic API with model %s", model)
        return anthropic.Anthropic(), model
    elif model.startswith("bedrock") and "claude" in model:
        client_model = model.split("/")[-1]
        logger.info("Using Amazon Bedrock with model %s", client_model)
        return anthropic.AnthropicBedrock(), client_model
    elif model.startswith("vertex_ai") and "claude" in model:
        client_model = model.split("/")[-1]
        logger.info("Using Vertex AI with model %s", client_model)
        return anthropic.AnthropicVertex(), client_model
    elif model.startswith("ollama/"):
        logger.info("Using Ollama with model %s", model)
        return openai.OpenAI(
            api_key=os.environ.get("OLLAMA_API_KEY", ""),
            base_url="http://localhost:11434/v1",
        ), model
    elif "gpt" in model:
        logger.info("Using OpenAI API with model %s", model)
        return openai.OpenAI(), model
    elif "o1" in model or "o3" in model:
        logger.info("Using OpenAI API with model %s", model)
        return openai.OpenAI(), model
    elif model == "deepseek-coder-v2-0724":
        logger.info("Using DeepSeek API with model %s", model)
        return openai.OpenAI(
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url="https://api.deepseek.com",
        ), model
    elif model == "deepcoder-14b":
        logger.info("Using HuggingFace API with model %s", model)
        if "HUGGINGFACE_API_KEY" not in os.environ:
            raise ValueError("HUGGINGFACE_API_KEY environment variable not set")
        return openai.OpenAI(
            api_key=os.environ["HUGGINGFACE_API_KEY"],
            base_url="https://api-inference.huggingface.co/models/agentica-org/DeepCoder-14B-Preview",
        ), model
    elif model == "llama3.1-405b":
        logger.info("Using OpenRouter API with model %s", model)
        return openai.OpenAI(
            api_key=os.environ["OPENROUTER_API_KEY"],
            base_url="https://openrouter.ai/api/v1",
        ), "meta-llama/llama-3.1-405b-instruct"
    elif "gemini" in model:
        logger.info("Using Gemini API with model %s", model)
        return openai.OpenAI(
            api_key=os.environ["GEMINI_API_KEY"],
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        ), model
    else:
        raise ValueError(f"Model {model} not supported. See AVAILABLE_LLMS for options.")


@backoff.on_exception(
    backoff.expo,
    (
        openai.RateLimitError,
        openai.APITimeoutError,
        openai.InternalServerError,
        anthropic.RateLimitError,
    ),
    max_tries=8,
)
def get_response_from_llm(
    prompt: str,
    client: Any,
    model: str,
    system_message: str,
    msg_history: list[dict[str, Any]] | None = None,
    temperature: float = 0.7,
    max_tokens: int = MAX_NUM_TOKENS,
) -> tuple[str, list[dict[str, Any]]]:
    """Send a prompt to the LLM and return (response_text, updated_msg_history)."""
    if msg_history is None:
        msg_history = []

    # --- Anthropic Claude (direct / Bedrock / Vertex) ---
    if "claude" in model:
        new_msg_history = msg_history + [
            {"role": "user", "content": [{"type": "text", "text": prompt}]}
        ]
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_message,
            messages=new_msg_history,
        )
        content = response.content[0].text
        new_msg_history = new_msg_history + [
            {"role": "assistant", "content": [{"type": "text", "text": content}]}
        ]
        return content, new_msg_history

    # --- Ollama ---
    if model.startswith("ollama/"):
        new_msg_history = msg_history + [{"role": "user", "content": prompt}]
        response = client.chat.completions.create(
            model=model.replace("ollama/", ""),
            messages=[{"role": "system", "content": system_message}, *new_msg_history],
            temperature=temperature,
            max_tokens=max_tokens,
            n=1,
        )
        content = response.choices[0].message.content
        new_msg_history = new_msg_history + [{"role": "assistant", "content": content}]
        return content, new_msg_history

    # --- OpenAI reasoning models (o1/o3) ---
    if "o1" in model or "o3" in model:
        new_msg_history = msg_history + [{"role": "user", "content": prompt}]
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": system_message}, *new_msg_history],
            temperature=1,
            n=1,
            seed=0,
        )
        content = response.choices[0].message.content
        new_msg_history = new_msg_history + [{"role": "assistant", "content": content}]
        return content, new_msg_history

    # --- GPT models (including gpt-5.2 / gpt-5.2-pro with reasoning "thinking") ---
    if "gpt" in model:
        new_msg_history = msg_history + [{"role": "user", "content": prompt}]
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "system", "content": system_message}, *new_msg_history],
            "n": 1,
            "seed": 0,
        }
        # GPT-5.2 / gpt-5.2-pro: only temperature=1 supported; use max_completion_tokens + reasoning
        if model.startswith("gpt-5.2"):
            kwargs["temperature"] = 1
            kwargs["max_completion_tokens"] = max_tokens
            kwargs["reasoning_effort"] = "high"
        else:
            kwargs["temperature"] = temperature
            kwargs["max_tokens"] = max_tokens
        response = client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        new_msg_history = new_msg_history + [{"role": "assistant", "content": content}]
        return content, new_msg_history

    # --- Gemini ---
    if "gemini" in model:
        new_msg_history = msg_history + [{"role": "user", "content": prompt}]
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system_message}, *new_msg_history],
            temperature=temperature,
            max_tokens=max_tokens,
            n=1,
        )
        content = response.choices[0].message.content
        new_msg_history = new_msg_history + [{"role": "assistant", "content": content}]
        return content, new_msg_history

    # --- DeepSeek ---
    if model == "deepseek-coder-v2-0724":
        new_msg_history = msg_history + [{"role": "user", "content": prompt}]
        response = client.chat.completions.create(
            model="deepseek-coder",
            messages=[{"role": "system", "content": system_message}, *new_msg_history],
            temperature=temperature,
            max_tokens=max_tokens,
            n=1,
        )
        content = response.choices[0].message.content
        new_msg_history = new_msg_history + [{"role": "assistant", "content": content}]
        return content, new_msg_history

    # --- DeepCoder ---
    if model == "deepcoder-14b":
        new_msg_history = msg_history + [{"role": "user", "content": prompt}]
        try:
            response = client.chat.completions.create(
                model="agentica-org/DeepCoder-14B-Preview",
                messages=[{"role": "system", "content": system_message}, *new_msg_history],
                temperature=temperature,
                max_tokens=max_tokens,
                n=1,
            )
            content = response.choices[0].message.content
        except Exception:
            import requests as _requests

            headers = {
                "Authorization": f"Bearer {os.environ['HUGGINGFACE_API_KEY']}",
                "Content-Type": "application/json",
            }
            payload = {
                "inputs": {
                    "system": system_message,
                    "messages": [
                        {"role": m["role"], "content": m["content"]}
                        for m in new_msg_history
                    ],
                },
                "parameters": {
                    "temperature": temperature,
                    "max_new_tokens": max_tokens,
                    "return_full_text": False,
                },
            }
            resp = _requests.post(
                "https://api-inference.huggingface.co/models/agentica-org/DeepCoder-14B-Preview",
                headers=headers,
                json=payload,
            )
            if resp.status_code == 200:
                content = resp.json()["generated_text"]
            else:
                raise ValueError(f"Error from HuggingFace API: {resp.text}")
        new_msg_history = new_msg_history + [{"role": "assistant", "content": content}]
        return content, new_msg_history

    # --- Llama ---
    if model in ["meta-llama/llama-3.1-405b-instruct", "llama-3-1-405b-instruct"]:
        new_msg_history = msg_history + [{"role": "user", "content": prompt}]
        response = client.chat.completions.create(
            model="meta-llama/llama-3.1-405b-instruct",
            messages=[{"role": "system", "content": system_message}, *new_msg_history],
            temperature=temperature,
            max_tokens=max_tokens,
            n=1,
        )
        content = response.choices[0].message.content
        new_msg_history = new_msg_history + [{"role": "assistant", "content": content}]
        return content, new_msg_history

    raise ValueError(f"Model {model} not supported.")


def extract_json_between_markers(llm_output: str) -> dict | None:
    """Extract the first valid JSON block from ```json ... ``` markers, or fall back to any JSON object."""
    json_pattern = r"```json(.*?)```"
    matches = re.findall(json_pattern, llm_output, re.DOTALL)
    if not matches:
        json_pattern = r"\{.*?\}"
        matches = re.findall(json_pattern, llm_output, re.DOTALL)
    for json_string in matches:
        json_string = json_string.strip()
        try:
            return json.loads(json_string)
        except json.JSONDecodeError:
            try:
                cleaned = re.sub(r"[\x00-\x1F\x7F]", "", json_string)
                return json.loads(cleaned)
            except json.JSONDecodeError:
                continue
    return None
