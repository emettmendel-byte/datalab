from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.core.config import settings
from app.schemas import CleaningStep, Plan, PlanStep


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

    async def plan_lifecycle_with_fallback(self, goal: str, dataset_schema: dict) -> tuple[Plan, bool]:
        """
        Returns (plan, used_fallback).
        Falls back to deterministic local planning when Ollama is unavailable.
        """
        try:
            return await self.plan_lifecycle(goal, dataset_schema), False
        except Exception:
            return build_heuristic_plan(goal, dataset_schema), True

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

    async def suggest_cleaning_steps(
        self,
        instruction: str,
        dataset_schema: dict,
        sample_rows: list[dict],
        existing_steps: list[dict] | None = None,
    ) -> list[CleaningStep]:
        """
        Ask Ollama for safe, structured cleaning steps (JSON only).
        """
        system_prompt = """You are a data cleaning assistant.
Return strict JSON only with shape: {"steps":[...]}.

Allowed operation_type values:
DROP_COLUMNS, DROP_ROWS_WITH_MISSING, FILL_MISSING, CAST_TYPE, FILTER_ROWS, DEDUP_ROWS, STANDARDIZE_CATEGORIES, PARSE_DATES

Each step object must include:
- operation_type (one of allowed values)
- parameters (object; keep simple and explicit)
- description (non-technical)
- generated_code (optional string)

Rules:
- Prefer 1-6 safe steps.
- Do not use arbitrary code execution.
- Use schema/sample context.
- If existing_steps are provided, improve/normalize them rather than inventing unrelated actions.
"""
        user_payload = {
            "instruction": instruction,
            "dataset_schema": dataset_schema,
            "sample_rows": sample_rows[:100],
            "existing_steps": existing_steps or [],
        }
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ]
        content = await self._client.chat(self._model, messages)
        obj = _extract_json_object(content)
        raw_steps = obj.get("steps", [])
        if not isinstance(raw_steps, list):
            raise ValueError("Invalid cleaning steps output.")

        steps: list[CleaningStep] = []
        for step in raw_steps[:10]:
            if not isinstance(step, dict):
                continue
            try:
                steps.append(CleaningStep.model_validate(step))
            except Exception:
                continue
        if not steps:
            raise ValueError("No valid cleaning steps returned by model.")
        return steps

    async def diagnose_data_messiness(
        self,
        instruction: str,
        dataset_schema: dict,
        sample_rows: list[dict],
    ) -> str:
        """
        Ask Ollama for plain-language messiness diagnostics.
        """
        system_prompt = """You are a data quality assistant for non-technical users.
Respond in concise plain language with:
1) likely messy areas
2) why they matter
3) practical cleaning suggestions

Keep it under 220 words. No code fences.
"""
        user_payload = {
            "instruction": instruction,
            "dataset_schema": dataset_schema,
            "sample_rows": sample_rows[:120],
        }
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ]
        return (await self._client.chat(self._model, messages)).strip()

    async def suggest_explore_questions(self, dataset_schema: dict, sample_rows: list[dict]) -> list[str]:
        system_prompt = """You are an analyst assistant for non-technical users.
Return strict JSON only: {"questions":[...]} with 4-8 concise, useful data questions.
Focus on trends, drivers, anomalies, and segment differences."""
        payload = {"dataset_schema": dataset_schema, "sample_rows": sample_rows[:80]}
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        content = await self._client.chat(self._model, messages)
        data = _extract_json_object(content)
        qs = data.get("questions", [])
        if not isinstance(qs, list):
            raise ValueError("Invalid questions output.")
        out = [str(q).strip() for q in qs if str(q).strip()]
        if not out:
            raise ValueError("No questions returned.")
        return out[:8]

    async def answer_explore_question(
        self,
        question: str,
        dataset_schema: dict,
        sample_rows: list[dict],
        profile: dict,
    ) -> str:
        system_prompt = """You are a data analyst tutor for non-technical users.
Answer the user's question in plain language using provided sample/profile context only.
Keep under 220 words. If uncertain, say it's sample-based and suggest a verification step."""
        payload = {
            "question": question,
            "dataset_schema": dataset_schema,
            "sample_rows": sample_rows[:120],
            "profile": profile,
        }
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        return (await self._client.chat(self._model, messages)).strip()

    async def suggest_summary_insights(self, profile: dict) -> list[dict]:
        system_prompt = """You are a data analyst assistant.
Return strict JSON only as {"insights":[...]}.
Each insight must include:
- type: one of "summary_stats", "correlation", "distribution"
- title: short title
- description: plain-language summary
- optional chart_suggestion with fields: chart_type, x, y, aggregation, description
Return 3-8 insights based on the profile."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps({"profile": profile}, ensure_ascii=False)},
        ]
        content = await self._client.chat(self._model, messages)
        data = _extract_json_object(content)
        raw = data.get("insights", [])
        if not isinstance(raw, list):
            raise ValueError("Invalid insights output.")
        return [x for x in raw if isinstance(x, dict)][:8]


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


def build_heuristic_plan(goal: str, dataset_schema: dict) -> Plan:
    """
    Deterministic fallback plan used when LLM planning is unavailable.
    """
    cols = []
    if isinstance(dataset_schema, dict):
        raw = dataset_schema.get("columns")
        if isinstance(raw, list):
            cols = [c.get("name") for c in raw if isinstance(c, dict) and c.get("name")]

    numeric_cols = []
    for c in dataset_schema.get("columns", []) if isinstance(dataset_schema, dict) else []:
        dtype = str(c.get("dtype", "")).lower()
        if any(x in dtype for x in ["int", "float", "double", "number"]):
            numeric_cols.append(c.get("name"))

    target_guess = cols[-1] if cols else "target"
    g = (goal or "").lower()
    model_op = "train_regression"
    model_code = f"# Train a baseline model to predict '{target_guess}'"
    if any(k in g for k in ["classify", "churn", "fraud", "yes/no", "probability"]):
        model_op = "train_classification"
        model_code = f"# Train a baseline classifier to predict '{target_guess}'"

    vis_hint = "Compare key numeric fields and category breakdowns."
    if numeric_cols:
        vis_hint = f"Start with distributions for {', '.join([str(x) for x in numeric_cols[:2]])} and one comparison chart."

    steps = [
        PlanStep(
            tab="Question",
            operation_type="clarify_goal",
            short_title="Confirm analysis goal",
            user_friendly_explanation="We will confirm the business question, success criteria, and what decision this analysis should support.",
            narrative_instructions="Confirm your end goal and what action you want to take from the result.",
        ),
        PlanStep(
            tab="Data",
            operation_type="preview_data",
            short_title="Inspect dataset and schema",
            user_friendly_explanation="We will verify column names, data types, and a quick sample to ensure the dataset loaded correctly.",
            python_pandas_code="df.head(50)",
        ),
        PlanStep(
            tab="Clean",
            operation_type="fill_missing",
            short_title="Fix missing and duplicate values",
            user_friendly_explanation="We will clean missing values, remove obvious duplicates, and normalize inconsistent text categories.",
            python_pandas_code="df = df.drop_duplicates()",
        ),
        PlanStep(
            tab="Explore",
            operation_type="eda_summary",
            short_title="Identify important patterns",
            user_friendly_explanation="We will summarize distributions, relationships, and unusual values to understand what drives outcomes.",
            narrative_instructions="Review missingness, summary stats, and strongest correlations in plain language.",
        ),
        PlanStep(
            tab="Visualize",
            operation_type="chart_suggestions",
            short_title="Create simple explanatory charts",
            user_friendly_explanation="We will generate clear charts that help non-technical users understand key trends.",
            narrative_instructions=vis_hint,
        ),
        PlanStep(
            tab="Model",
            operation_type=model_op,
            short_title="Train a baseline model",
            user_friendly_explanation="We will train a simple baseline model and report easy-to-understand quality metrics.",
            sklearn_code=model_code,
        ),
        PlanStep(
            tab="Report",
            operation_type="write_report",
            short_title="Summarize findings and next steps",
            user_friendly_explanation="We will produce a short narrative report with conclusions, limitations, and practical next steps.",
            narrative_instructions="Write a concise report for non-technical stakeholders.",
        ),
    ]
    return Plan(steps=steps)

