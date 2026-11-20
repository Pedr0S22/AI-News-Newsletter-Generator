import asyncio
import json
import re
import uuid
from typing import Any, AsyncGenerator, Optional
import httpx
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from api.configs.config import settings
from api.configs.logging import get_logger

logger = get_logger(__name__)


def parse_iaedu_stream_text(raw_text: str) -> str:
    """Parses IAedu's newline-delimited JSON event stream into final assistant text.

    Verified live wire format from api.iaedu.pt:
      {"run_id": "...", "type": "start", "content": "Processing"}
      {"run_id": "...", "type": "token", "content": "..."}
      {"run_id": "...", "type": "message", "content": {"type": "ai", "content": "<full text>"}}
    """
    final_message: Optional[str] = None
    tokens: list[str] = []

    blocks = re.split(r"\r?\n\r?\n|\r?\n", raw_text.strip())
    for block in blocks:
        line = block.strip()
        if not line:
            continue
        if line.startswith("data:"):
            line = line[5:].strip()
        if not line or line == "[DONE]":
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        if not isinstance(event, dict):
            continue

        evt_type = event.get("type")
        content = event.get("content")

        if evt_type == "message":
            if isinstance(content, dict) and isinstance(content.get("content"), str):
                final_message = content["content"]
            elif isinstance(content, str):
                final_message = content
        elif evt_type == "token" and isinstance(content, str):
            tokens.append(content)
        elif evt_type == "error":
            err_msg = content if isinstance(content, str) else json.dumps(content)
            raise RuntimeError(f"IAedu API returned stream error: {err_msg}")

    if final_message is not None:
        return final_message.strip()
    if tokens:
        return "".join(tokens).strip()
    return raw_text.strip()


def extract_json_object(text: str) -> Optional[dict[str, Any]]:
    """Extracts the first valid JSON object from raw model output (tolerating code fences)."""
    if not text:
        return None
    cleaned = text.strip()
    # Strip markdown code fences if present
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Fallback: locate outermost {...}
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(cleaned[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return None


def _stringify_system_instruction(sys_instr: Any) -> str:
    if not sys_instr:
        return ""
    if isinstance(sys_instr, str):
        return sys_instr.strip()
    if isinstance(sys_instr, types.Content) and sys_instr.parts:
        return "\n".join(p.text for p in sys_instr.parts if getattr(p, "text", None)).strip()
    if isinstance(sys_instr, list):
        chunks = []
        for item in sys_instr:
            if isinstance(item, str):
                chunks.append(item)
            elif hasattr(item, "text") and item.text:
                chunks.append(item.text)
        return "\n".join(chunks).strip()
    return str(sys_instr).strip()


class IAeduLlm(BaseLlm):
    """Custom Google ADK 2.x BaseLlm adapter for FCT/FCCN IAedu GPT-5.5 streaming API."""

    model: str = "iaedu-gpt-5.5"
    endpoint: str = ""
    api_key: str = ""
    channel_id: str = ""
    timeout_seconds: float = 90.0
    max_retries: int = 3

    @classmethod
    def supported_models(cls) -> list[str]:
        return [r"iaedu.*"]

    def _build_prompt_and_tool_names(self, llm_request: LlmRequest) -> tuple[str, set[str]]:
        sections: list[str] = []
        tool_names: set[str] = set()

        # 1. System Instruction
        sys_text = ""
        if llm_request.config and getattr(llm_request.config, "system_instruction", None):
            sys_text = _stringify_system_instruction(llm_request.config.system_instruction)
        if sys_text:
            sections.append(f"SYSTEM INSTRUCTIONS:\n{sys_text}")

        # 2. Tool Bridge (translates ADK tools like exit_loop into explicit JSON call contract)
        tools_dict = getattr(llm_request, "tools_dict", None) or {}
        if tools_dict:
            tool_lines = [
                "AVAILABLE TOOLS:",
                "If you need to invoke one of the tools below, respond with ONLY valid JSON in the exact format:",
                '{"tool_call": {"name": "<tool_name>", "args": {}}}',
                "Tools:",
            ]
            for t_name, tool_obj in tools_dict.items():
                tool_names.add(t_name)
                desc = getattr(tool_obj, "description", "") or ""
                tool_lines.append(f"- {t_name}: {desc}")
            sections.append("\n".join(tool_lines))

        # 3. Conversation Contents
        convo_lines: list[str] = []
        for content in llm_request.contents or []:
            role = (getattr(content, "role", None) or "user").upper()
            part_texts: list[str] = []
            for part in content.parts or []:
                if getattr(part, "text", None):
                    part_texts.append(part.text)
                elif getattr(part, "function_call", None):
                    fc = part.function_call
                    part_texts.append(f"[TOOL_CALL {fc.name}({json.dumps(fc.args or {})})]")
                elif getattr(part, "function_response", None):
                    fr = part.function_response
                    part_texts.append(f"[TOOL_RESULT {fr.name}: {json.dumps(fr.response or {})}]")
            if part_texts:
                convo_lines.append(f"{role}:\n" + "\n".join(part_texts))

        if convo_lines:
            sections.append("CONVERSATION:\n" + "\n\n".join(convo_lines))

        return "\n\n---\n\n".join(sections), tool_names

    async def _post_to_iaedu(self, message: str) -> str:
        endpoint = self.endpoint or settings.CHATGPT_55_ENDPOINT
        api_key = self.api_key or settings.CHATGPT_55_API_KEY
        channel_id = self.channel_id or settings.CHATGPT_55_CHANNEL_ID

        if not (endpoint and api_key and channel_id):
            raise RuntimeError(
                "IAedu credentials missing. Configure CHATGPT_55_ENDPOINT, "
                "CHATGPT_55_API_KEY, and CHATGPT_55_CHANNEL_ID in backend/.env."
            )

        last_exc: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            # Always use a fresh thread_id per stateless ADK call to prevent context leakage
            files = {
                "channel_id": (None, channel_id),
                "thread_id": (None, str(uuid.uuid4())),
                "user_info": (None, "{}"),
                "message": (None, message),
            }
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(
                        endpoint,
                        headers={"x-api-key": api_key},
                        files=files,
                    )
                    if response.status_code >= 400:
                        logger.warning(
                            f"IAedu HTTP {response.status_code} on attempt {attempt}/{self.max_retries}: "
                            f"{response.text[:300]}"
                        )
                    response.raise_for_status()
                    return parse_iaedu_stream_text(response.text)
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    f"IAedu request failed (attempt {attempt}/{self.max_retries}): {exc}"
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(1.5 * attempt)

        raise RuntimeError(f"IAedu request failed after {self.max_retries} attempts: {last_exc}")

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        """Executes a single ADK LLM turn against IAedu GPT-5.5 and yields an LlmResponse."""
        prompt, tool_names = self._build_prompt_and_tool_names(llm_request)
        reply_text = await self._post_to_iaedu(prompt)

        # Check if the model emitted a structured JSON tool call matching an ADK tool
        if tool_names:
            parsed = extract_json_object(reply_text)
            if parsed and isinstance(parsed.get("tool_call"), dict):
                tc = parsed["tool_call"]
                tc_name = tc.get("name")
                tc_args = tc.get("args") if isinstance(tc.get("args"), dict) else {}
                if tc_name in tool_names:
                    logger.info(f"IAeduLlm translated tool_call -> {tc_name}({tc_args})")
                    yield LlmResponse(
                        content=types.Content(
                            role="model",
                            parts=[types.Part.from_function_call(name=tc_name, args=tc_args)],
                        )
                    )
                    return

        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(text=reply_text)],
            )
        )


def get_iaedu_llm() -> IAeduLlm:
    """Factory returning the configured IAedu GPT-5.5 BaseLlm instance."""
    return IAeduLlm(
        model="iaedu-gpt-5.5",
        endpoint=settings.CHATGPT_55_ENDPOINT,
        api_key=settings.CHATGPT_55_API_KEY,
        channel_id=settings.CHATGPT_55_CHANNEL_ID,
    )


def get_ollama_llm() -> BaseLlm:
    """Factory returning a Google ADK LiteLlm connected to local Ollama (host GPU)."""
    from google.adk.models.lite_llm import LiteLlm

    kwargs: dict[str, Any] = {
        "model": f"openai/{settings.OLLAMA_MODEL}",
        "api_base": settings.OLLAMA_BASE_URL,
        "api_key": "ollama",
        "temperature": 0,
    }
    if settings.OLLAMA_REASONING_EFFORT:
        kwargs["reasoning_effort"] = settings.OLLAMA_REASONING_EFFORT
    return LiteLlm(**kwargs)


def get_eval_llm() -> BaseLlm:
    """Returns the LLM configured for high-volume Evaluation Agents (default: local Ollama)."""
    provider = (settings.EVAL_LLM_PROVIDER or "ollama").strip().lower()
    if provider == "iaedu":
        logger.debug("Evaluation pipeline using IAedu GPT-5.5.")
        return get_iaedu_llm()
    logger.debug(
        f"Evaluation pipeline using local Ollama model '{settings.OLLAMA_MODEL}' "
        f"at {settings.OLLAMA_BASE_URL}."
    )
    return get_ollama_llm()


def get_writer_llm() -> BaseLlm:
    """Returns the LLM configured for Newsletter Drafting & Reflection (default: IAedu GPT-5.5)."""
    provider = (settings.WRITER_LLM_PROVIDER or "iaedu").strip().lower()
    if provider == "ollama":
        logger.debug(
            f"Newsletter synthesis using local Ollama model '{settings.OLLAMA_MODEL}'."
        )
        return get_ollama_llm()
    logger.debug("Newsletter synthesis using IAedu GPT-5.5.")
    return get_iaedu_llm()
