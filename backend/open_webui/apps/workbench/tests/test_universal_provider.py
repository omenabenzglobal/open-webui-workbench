"""
Integration & Verification Test Harness: Universal Provider Ingress & Autonomous Tool Loop
Test Module: backend.open_webui.apps.workbench.tests.test_universal_provider
Directive: DIR-3.1-UNIVERSAL-PROVIDER-INGRESS
"""

import asyncio
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple
import urllib.error
import urllib.request
import pytest

# Ensure WEBUI_SECRET_KEY is present
os.environ.setdefault("WEBUI_SECRET_KEY", "test-secret-key-for-provider-tests")

# Dynamically discover provider credentials from environment or registry
def get_active_provider_credentials() -> Dict[str, str]:
    """
    Dynamically scans environment variables and user registry for active provider keys
    without hardcoding secrets or logging sensitive values.
    """
    creds = {}
    known_keys = [
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GROQ_API_KEY",
        "DEEPSEEK_API_KEY",
    ]
    for k in known_keys:
        val = os.environ.get(k)
        if val:
            creds[k] = val

    # If on Windows, also check User Environment registry
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as reg_key:
                for k in known_keys:
                    if k not in creds:
                        try:
                            val, _ = winreg.QueryValueEx(reg_key, k)
                            if val:
                                creds[k] = val
                                os.environ[k] = val
                        except FileNotFoundError:
                            pass
        except Exception:
            pass

    return creds


ACTIVE_CREDS = get_active_provider_credentials()

from open_webui.apps.workbench.tools.workspace_tools import Tools
from open_webui.routers.openai import get_models_request
from open_webui.utils.tools import get_tool_specs


# ─────────────────────────────────────────────────────────────────────────────
# Helper: Thinking / Reasoning Extractor
# ─────────────────────────────────────────────────────────────────────────────

def extract_thinking_and_content(stream_chunks: List[Dict[str, Any]]) -> Tuple[str, str]:
    """
    Extracts and separates reasoning/thinking tokens and visible content tokens
    from a sequence of streaming chunk payloads.
    Supports:
    - Native `delta.reasoning_content` (DeepSeek-R1 / OpenAI-compatible reasoning)
    - Inline `<think>...</think>` or `<thought>...</thought>` tags inside content
    """
    thinking_raw = ""
    content_raw = ""

    for chunk in stream_chunks:
        choices = chunk.get("choices", [])
        if not choices:
            continue
        delta = choices[0].get("delta", {})

        # Native reasoning field — concatenate directly (streaming fragments)
        reasoning = delta.get("reasoning_content") or delta.get("reasoning") or delta.get("thinking")
        if reasoning:
            thinking_raw += str(reasoning)

        # Standard content — concatenate directly
        c = delta.get("content")
        if c:
            content_raw += str(c)

    # Check for inline think tags in the accumulated content
    think_pattern = re.compile(r"<(think|thought)>(.*?)(?:</\1>|$)", re.DOTALL | re.IGNORECASE)
    matches = think_pattern.findall(content_raw)
    inline_thinking_parts: List[str] = []
    for _, think_body in matches:
        if think_body.strip():
            inline_thinking_parts.append(think_body.strip())

    visible_content = re.sub(r"<(think|thought)>.*?(?:</\1>|$)", "", content_raw, flags=re.DOTALL | re.IGNORECASE).strip()

    # Combine native reasoning (concatenated) and inline tag thinking (newline-separated sources)
    all_parts: List[str] = []
    if thinking_raw.strip():
        all_parts.append(thinking_raw.strip())
    all_parts.extend(inline_thinking_parts)
    joined_thinking = "\n".join(all_parts).strip()

    return joined_thinking, visible_content


class RateLimitError(Exception):
    """Raised when provider returns 429 after all retries are exhausted."""
    pass


def execute_llm_request_with_retry(
    url: str,
    payload: Dict[str, Any],
    api_key: str,
    max_retries: int = 5,
) -> Dict[str, Any]:
    """
    Executes an HTTP POST chat completion request with exponential backoff on 503/429.
    Raises RateLimitError if all retries fail due to rate limiting.
    """
    req_data = json.dumps(payload).encode("utf-8")
    for attempt in range(max_retries):
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            data=req_data,
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (503, 429) and attempt < max_retries - 1:
                wait_sec = (attempt + 1) * 15
                time.sleep(wait_sec)
                continue
            if e.code == 429:
                raise RateLimitError(f"Rate limited (429) after {max_retries} retries") from e
            raise



# ─────────────────────────────────────────────────────────────────────────────
# 1. Dynamic Model Discovery
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dynamic_model_discovery():
    """
    Verify Open WebUI's router can query /models against active provider endpoints
    and dynamically discover model catalogs without hardcoding.
    """
    gemini_key = ACTIVE_CREDS.get("GEMINI_API_KEY") or ACTIVE_CREDS.get("GOOGLE_API_KEY")
    openai_key = ACTIVE_CREDS.get("OPENAI_API_KEY")

    if not gemini_key and not openai_key:
        pytest.skip("No live provider API keys available for discovery test.")

    endpoint_url = "https://generativelanguage.googleapis.com/v1beta/openai" if gemini_key else "https://api.openai.com/v1"
    active_key = gemini_key or openai_key

    # Query through Open WebUI's router function
    result = await get_models_request(
        request=None,
        url=endpoint_url,
        key=active_key,
        user=None,
    )

    assert isinstance(result, dict), "Expected dict response from router get_models_request"
    assert "data" in result, f"Expected 'data' key in response, got: {list(result.keys())}"

    models = result["data"]
    assert len(models) > 0, "Discovered model list should not be empty"

    # Verify model structure
    first_model = models[0]
    assert "id" in first_model, "Model entry must contain an 'id'"
    assert isinstance(first_model["id"], str)

    # Verify catalog contains recognizable models
    model_ids = [m["id"] for m in models]
    if gemini_key:
        assert any("flash" in m.lower() or "gemini" in m.lower() for m in model_ids)
    elif openai_key:
        assert any("gpt" in m.lower() for m in model_ids)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Streaming & Thinking Extraction
# ─────────────────────────────────────────────────────────────────────────────

def test_thinking_extraction_unit_logic():
    """
    Unit test verifying separation of reasoning tokens and content deltas
    for both native reasoning_content and inline <think> tags.
    """
    # Case 1: Native reasoning_content (DeepSeek R1 / Groq)
    native_chunks = [
        {"choices": [{"delta": {"reasoning_content": "Evaluating ", "content": None}}]},
        {"choices": [{"delta": {"reasoning_content": "mathematical factorial...", "content": None}}]},
        {"choices": [{"delta": {"reasoning_content": None, "content": "The result "}}]},
        {"choices": [{"delta": {"reasoning_content": None, "content": "is 120."}}]},
    ]
    thinking_1, content_1 = extract_thinking_and_content(native_chunks)
    assert "Evaluating mathematical factorial..." in thinking_1
    assert content_1 == "The result is 120."

    # Case 2: Inline <think> tags inside content stream
    tag_chunks = [
        {"choices": [{"delta": {"content": "<think>First plan the solution."}}]},
        {"choices": [{"delta": {"content": " Use recursion.</think>Factorial of 5 is 120."}}]},
    ]
    thinking_2, content_2 = extract_thinking_and_content(tag_chunks)
    assert "First plan the solution. Use recursion." in thinking_2
    assert content_2 == "Factorial of 5 is 120."


@pytest.mark.asyncio
async def test_live_streaming_completion():
    """
    Verify live streaming completion against active provider endpoint,
    parsing SSE tokens and validating final reconstructed response.
    """
    gemini_key = ACTIVE_CREDS.get("GEMINI_API_KEY") or ACTIVE_CREDS.get("GOOGLE_API_KEY")
    if not gemini_key:
        pytest.skip("No Gemini API key available for live streaming test.")

    payload = {
        "model": "models/gemini-flash-latest",
        "messages": [{"role": "user", "content": "What is 3 + 3? Respond with just the number."}],
        "stream": True,
    }

    url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

    chunks: List[Dict[str, Any]] = []
    last_error = None
    for attempt in range(5):
        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {gemini_key}",
                "Content-Type": "application/json",
            },
            data=req_data,
        )
        try:
            chunks = []
            with urllib.request.urlopen(req, timeout=60) as resp:
                for line in resp:
                    line_str = line.decode("utf-8").strip()
                    if line_str.startswith("data: ") and line_str != "data: [DONE]":
                        try:
                            data = json.loads(line_str[6:])
                            chunks.append(data)
                        except Exception:
                            continue
            last_error = None
            break
        except urllib.error.HTTPError as e:
            last_error = e
            if e.code in (429, 503) and attempt < 4:
                time.sleep((attempt + 1) * 15)
                continue
            break

    if last_error and last_error.code == 429:
        pytest.skip("Rate limited (429) during streaming test — free-tier throttling")
    if last_error:
        raise last_error

    assert len(chunks) > 0, "Expected multiple streaming chunks from provider"
    thinking, content = extract_thinking_and_content(chunks)
    assert "6" in content, f"Expected '6' in streamed response, got: {content}"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Autonomous Multi-Turn Tool Execution Round-Trip
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_autonomous_multi_turn_tool_roundtrip():
    """
    Verify complete autonomous multi-turn tool calling loop:
    1. Model receives engineering instruction and emits write_file tool call.
    2. Runtime safely creates test_calc.py in isolated workspace.
    3. Model evaluates write receipt and emits execute_command tool call.
    4. Runtime executes command in isolated subprocess and returns receipt with exit code 0.
    5. Model evaluates program output and produces final confirmation.
    """
    gemini_key = ACTIVE_CREDS.get("GEMINI_API_KEY") or ACTIVE_CREDS.get("GOOGLE_API_KEY")
    if not gemini_key:
        pytest.skip("No Gemini API key available for live multi-turn tool test.")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tools = Tools()
        tools.valves.WORKSPACE_ROOT = tmp_dir
        tools.valves.EXECUTION_MODE = "AUTONOMOUS"

        specs = get_tool_specs(tools)
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": s["name"],
                    "description": s["description"],
                    "parameters": s["parameters"],
                },
            }
            for s in specs
        ]

        messages: List[Dict[str, Any]] = [
            {
                "role": "user",
                "content": (
                    "In the workspace, create a file test_calc.py that contains a function "
                    "calculating factorials and prints the factorial of 5. "
                    "Then run this script using python via execute_command and report the result."
                ),
            }
        ]

        endpoint_url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        executed_tools: List[str] = []
        final_answer: Optional[str] = None

        try:
            # Execute multi-turn loop up to 5 turns
            for step in range(5):
                payload = {
                    "model": "models/gemini-flash-latest",
                    "messages": messages,
                    "tools": openai_tools,
                    "tool_choice": "auto",
                }

                data = execute_llm_request_with_retry(endpoint_url, payload, gemini_key)
                msg = data["choices"][0]["message"]
                messages.append(msg)

                tool_calls = msg.get("tool_calls")
                if not tool_calls:
                    final_answer = msg.get("content")
                    break

                for tc in tool_calls:
                    fn_name = tc["function"]["name"]
                    args = json.loads(tc["function"]["arguments"])
                    tc_id = tc["id"]
                    executed_tools.append(fn_name)

                    if fn_name == "write_file":
                        res = await tools.write_file(args["path"], args["content"])
                    elif fn_name == "execute_command":
                        res = await tools.execute_command(args["command"])
                    elif fn_name == "read_file":
                        res = await tools.read_file(args["path"])
                    elif fn_name == "list_files":
                        res = await tools.list_files(args.get("subpath", "."))
                    else:
                        res = f"Error: Unknown tool {fn_name}"

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": res,
                    })
        except RateLimitError:
            pytest.skip("Rate limited (429) during multi-turn tool roundtrip — free-tier throttling")

        # Assertions on autonomous loop execution
        assert "write_file" in executed_tools, "write_file must be invoked by the model"
        assert "execute_command" in executed_tools, "execute_command must be invoked by the model"

        # Verify file creation on disk
        target_file = Path(tmp_dir) / "test_calc.py"
        assert target_file.exists(), "test_calc.py must exist in the workspace"
        file_content = target_file.read_text(encoding="utf-8")
        assert "def factorial" in file_content or "factorial" in file_content

        # Verify final answer mentions calculation result (120)
        assert final_answer is not None, "Model must provide a final answer"
        assert "120" in final_answer, f"Final answer must reference 120, got: {final_answer}"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Multi-Turn Self-Correction
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_multi_turn_self_correction():
    """
    Verify that when command execution returns a failure receipt (non-zero exit code),
    the model processes the diagnostic receipt and attempts corrective action.
    """
    gemini_key = ACTIVE_CREDS.get("GEMINI_API_KEY") or ACTIVE_CREDS.get("GOOGLE_API_KEY")
    if not gemini_key:
        pytest.skip("No Gemini API key available for self-correction test.")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tools = Tools()
        tools.valves.WORKSPACE_ROOT = tmp_dir
        tools.valves.EXECUTION_MODE = "AUTONOMOUS"

        specs = get_tool_specs(tools)
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": s["name"],
                    "description": s["description"],
                    "parameters": s["parameters"],
                },
            }
            for s in specs
        ]

        # Initial intentionally broken file
        broken_file = Path(tmp_dir) / "broken.py"
        broken_file.write_text("print(undefined_variable)\n", encoding="utf-8")

        messages: List[Dict[str, Any]] = [
            {
                "role": "user",
                "content": (
                    "In the workspace, there is a script broken.py. Run it using execute_command. "
                    "If it encounters an error, fix the file using write_file and run it again."
                ),
            }
        ]

        endpoint_url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        command_runs = 0

        try:
            for step in range(5):
                payload = {
                    "model": "models/gemini-flash-latest",
                    "messages": messages,
                    "tools": openai_tools,
                    "tool_choice": "auto",
                }

                data = execute_llm_request_with_retry(endpoint_url, payload, gemini_key)
                msg = data["choices"][0]["message"]
                messages.append(msg)

                tool_calls = msg.get("tool_calls")
                if not tool_calls:
                    break

                for tc in tool_calls:
                    fn_name = tc["function"]["name"]
                    args = json.loads(tc["function"]["arguments"])
                    tc_id = tc["id"]

                    if fn_name == "execute_command":
                        command_runs += 1
                        res = await tools.execute_command(args["command"])
                    elif fn_name == "write_file":
                        res = await tools.write_file(args["path"], args["content"])
                    elif fn_name == "read_file":
                        res = await tools.read_file(args["path"])
                    else:
                        res = "ok"

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": res,
                    })
        except RateLimitError:
            pytest.skip("Rate limited (429) during self-correction test — free-tier throttling")

        # Verify model attempted execution at least once and attempted self-correction
        assert command_runs >= 1, "Expected model to execute command"
        fixed_content = broken_file.read_text(encoding="utf-8")
        assert "undefined_variable" not in fixed_content or command_runs >= 2

