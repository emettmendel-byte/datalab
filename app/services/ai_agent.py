from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.core.config import settings
from app.schemas import Plan, PlanStep


class OllamaClient:
    def __init__(self) -> None:
        self._base_url = settings.ollama_base_url.rstrip("/")

    async def generate(self, model: str, prompt: str) -> str:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self._base_url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "")

    async def chat(self, model: str, messages: list[dict[str, Any]]) -> str:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self._base_url}/api/chat",
                json={"model": model, "messages": messages, "stream": False},
            )
            resp.raise_for_status()
            data = resp.json()
            msg = data.get("message") or {}
            return msg.get("content", "")


_SYSTEM_PROMPT = """You are a friendly data-science tutor for non-technical users.
You MUST output strict JSON only (no markdown, no code fences, no extra text).

Your task: create a lifecycle plan to achieve the user's goal on their dataset.
Return an object with a single key: "steps".

Each step MUST be an object with:
- tab: one of ["Question","Data","Clean","Explore","Visualize","Model","Report"]
- operation_type: a short machine-friendly label (e.g., "eda_summary", "missing_values", "train_model", "write_report")
- short_title: a short human title
- user_friendly_explanation: 1-3 sentences, non-technical
- and exactly ONE of the following fields:
  - python_pandas_code (string)
  - sklearn_code (string)
  - narrative_instructions (string)

Rules:
- Do NOT execute anything. Only propose steps.
- Keep code minimal and safe. No file system access. No network calls.
- If you don't have enough info, include a "Question" tab step asking the user for it via narrative_instructions.
"""


class DataScienceAgent:
    def __init__(self, *, model: str | None = None) -> None:
        self._client = OllamaClient()
        self._model = model or settings.ollama_model

    async def plan_lifecycle(self, goal: str, dataset_schema: dict) -> Plan:
        user_payload = {"goal": goal, "dataset_schema": dataset_schema}
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_payload)},
        ]
        content = await self._client.chat(self._model, messages)
        data = _extract_json_object(content)
        plan = Plan.model_validate(data)
        _validate_plan_steps(plan.steps)
        return plan

    async def explain_step(self, step: PlanStep) -> str:
        explain_prompt = """Explain this plan step to a non-technical user in plain English (2-4 sentences).
Do not include JSON. Do not include code. Focus on why this step matters."""
        messages = [
            {"role": "system", "content": explain_prompt},
            {"role": "user", "content": json.dumps(step.model_dump())},
        ]
        return (await self._client.chat(self._model, messages)).strip()

    async def generate_report_markdown(self, report_context: dict) -> str:
        system_prompt = """You are a data-science tutor writing for non-technical users.
Write a markdown report with the EXACT section headings below:

## Question
## Data
## Clean
## Explore
## Visualize
## Model
## Report

Requirements:
- Keep the full report under 1000 words.
- Use simple language.
- Avoid formulas.
- If you use technical jargon, immediately explain it in plain words in parentheses.
- Be honest about uncertainty and limitations.
- In "Report", provide conclusions and practical next steps.
- Return markdown only (no JSON, no code fences).
"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(report_context, ensure_ascii=False)},
        ]
        return (await self._client.chat(self._model, messages)).strip()


def _extract_json_object(text: str) -> dict:
    """
    Ollama should return strict JSON, but this defensively extracts the first JSON object.
    """
    text = text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise ValueError("Agent did not return JSON.")
    snippet = m.group(0)
    data = json.loads(snippet)
    if not isinstance(data, dict):
        raise ValueError("Agent JSON root must be an object.")
    return data


def _validate_plan_steps(steps: list[PlanStep]) -> None:
    allowed_tabs = {"Question", "Data", "Clean", "Explore", "Visualize", "Model", "Report"}
    for i, s in enumerate(steps):
        if s.tab not in allowed_tabs:
            raise ValueError(f"Invalid tab in step {i}: {s.tab}")

        code_fields = [s.python_pandas_code, s.sklearn_code, s.narrative_instructions]
        present = sum(1 for v in code_fields if v is not None and str(v).strip() != "")
        if present != 1:
            raise ValueError(f"Step {i} must include exactly one of python_pandas_code, sklearn_code, or narrative_instructions.")

