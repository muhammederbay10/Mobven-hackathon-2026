# ai/extractors.py
"""Runs focused vision extractors concurrently with retries and optional rules witnessing."""

from __future__ import annotations

import asyncio
import base64
import inspect
import json
import os
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from pydantic import BaseModel, ValidationError

if __package__:
    from .chunker import Chunk
    from .prompts import appointments, rules, specimens
    from .prompts.common import RETRY_TEMPLATE
    from .schema import (
        AgentOutput,
        AppointmentsAgentOutput,
        ChunkExtractionResult,
        ExtractorAgent,
        ExtractorProgress,
        ExtractorRole,
        ExtractorStatus,
        ProgressState,
        RulesAgentOutput,
        SpecimensAgentOutput,
    )
else:  # uvicorn main:app started from inside ai/
    from chunker import Chunk
    from prompts import appointments, rules, specimens
    from prompts.common import RETRY_TEMPLATE
    from schema import (
        AgentOutput,
        AppointmentsAgentOutput,
        ChunkExtractionResult,
        ExtractorAgent,
        ExtractorProgress,
        ExtractorRole,
        ExtractorStatus,
        ProgressState,
        RulesAgentOutput,
        SpecimensAgentOutput,
    )


MAX_ATTEMPTS = 2
DEFAULT_MAX_CONCURRENCY = 4
VISION_DETAIL = "high"

ModelCaller = Callable[
    [Chunk, ExtractorRole, str, str, list[dict[str, Any]]], Awaitable[str]
]
ProgressCallback = Callable[[ExtractorProgress], Awaitable[None] | None]


class ExtractorConfigurationError(RuntimeError):
    """Raised when required extractor configuration is absent."""


async def extract_chunks(
    chunks: Sequence[Chunk],
    *,
    call_model: ModelCaller | None = None,
    extraction_model: str | None = None,
    witness_model: str | None = None,
    max_concurrency: int | None = None,
    progress: ProgressCallback | None = None,
) -> list[ChunkExtractionResult]:
    """Extracts all chunks without allowing one failed model call to cancel its siblings."""

    primary_model = _resolve_primary_model(extraction_model)
    resolved_witness = _resolve_witness_model(witness_model)
    semaphore = asyncio.Semaphore(_resolve_max_concurrency(max_concurrency))
    caller = call_model or _default_caller
    jobs: list[Awaitable[ChunkExtractionResult]] = []

    for chunk in chunks:
        if chunk.agent == ExtractorAgent.REVIEW:
            jobs.append(_skip_review_chunk(chunk, progress))
            continue
        jobs.append(
            _extract_one(
                chunk,
                role=ExtractorRole.PRIMARY,
                model=primary_model,
                caller=caller,
                semaphore=semaphore,
                progress=progress,
            )
        )
        if chunk.agent == ExtractorAgent.RULES and resolved_witness:
            jobs.append(
                _extract_one(
                    chunk,
                    role=ExtractorRole.WITNESS,
                    model=resolved_witness,
                    caller=caller,
                    semaphore=semaphore,
                    progress=progress,
                )
            )

    return list(await asyncio.gather(*jobs))


async def _extract_one(
    chunk: Chunk,
    *,
    role: ExtractorRole,
    model: str,
    caller: ModelCaller,
    semaphore: asyncio.Semaphore,
    progress: ProgressCallback | None,
) -> ChunkExtractionResult:
    agent = ExtractorAgent(chunk.agent)
    await _emit(progress, chunk, role, ProgressState.RUNNING, "started")
    raw_responses: list[str] = []
    validation_error = ""

    for attempt in range(1, MAX_ATTEMPTS + 1):
        system_prompt, instruction = _prompt_for(chunk)
        if role is ExtractorRole.WITNESS:
            instruction = f"{instruction}\n\n{rules.WITNESS_NOTE}"
        if validation_error:
            instruction = f"{instruction}\n\n{RETRY_TEMPLATE.format(error=validation_error)}"
        content = _user_content(chunk, instruction)
        try:
            async with semaphore:
                raw = await caller(chunk, role, model, system_prompt, content)
            raw_responses.append(raw)
            output = _parse_output(chunk, raw)
        except Exception as error:  # each chunk degrades independently after its single retry
            validation_error = _describe_error(error)
            if attempt < MAX_ATTEMPTS:
                continue
            await _emit(progress, chunk, role, ProgressState.FAILED, validation_error)
            return ChunkExtractionResult(
                chunk_id=chunk.chunk_id,
                agent=agent,
                role=role,
                status=ExtractorStatus.FAILED,
                model=model,
                supporting_only=chunk.supporting_only,
                attempts=attempt,
                chunk_failed=True,
                error=validation_error,
                raw_responses=raw_responses,
            )

        detail = _success_detail(output)
        await _emit(progress, chunk, role, ProgressState.DONE, detail)
        return ChunkExtractionResult(
            chunk_id=chunk.chunk_id,
            agent=agent,
            role=role,
            status=ExtractorStatus.SUCCESS,
            model=model,
            supporting_only=chunk.supporting_only,
            attempts=attempt,
            output=output,
            raw_responses=raw_responses,
        )

    raise AssertionError("extractor retry loop exited unexpectedly")


async def _skip_review_chunk(
    chunk: Chunk, progress: ProgressCallback | None
) -> ChunkExtractionResult:
    detail = "other_unknown page requires human review"
    await _emit(progress, chunk, ExtractorRole.PRIMARY, ProgressState.SKIPPED, detail)
    return ChunkExtractionResult(
        chunk_id=chunk.chunk_id,
        agent=ExtractorAgent.REVIEW,
        role=ExtractorRole.PRIMARY,
        status=ExtractorStatus.SKIPPED,
        supporting_only=chunk.supporting_only,
        attempts=0,
        error=detail,
    )


async def _emit(
    callback: ProgressCallback | None,
    chunk: Chunk,
    role: ExtractorRole,
    state: ProgressState,
    detail: str,
) -> None:
    if callback is None:
        return
    event = ExtractorProgress(
        name=f"extract:{chunk.agent}:{role.value}",
        state=state,
        detail=detail,
        chunk_id=chunk.chunk_id,
        role=role,
    )
    pending = callback(event)
    if inspect.isawaitable(pending):
        await pending


def _prompt_for(chunk: Chunk) -> tuple[str, str]:
    if chunk.agent == ExtractorAgent.APPOINTMENTS:
        return (
            appointments.SYSTEM_PROMPT,
            appointments.USER_INSTRUCTION.format(context_header=chunk.context_header),
        )
    if chunk.agent in {ExtractorAgent.RULES, ExtractorAgent.ANNEX}:
        supporting_note = rules.SUPPORTING_NOTE if chunk.supporting_only else rules.PRIMARY_NOTE
        return (
            rules.SYSTEM_PROMPT,
            rules.USER_INSTRUCTION.format(
                context_header=chunk.context_header,
                supporting_note=supporting_note,
            ),
        )
    if chunk.agent == ExtractorAgent.SPECIMENS:
        return (
            specimens.SYSTEM_PROMPT,
            specimens.USER_INSTRUCTION.format(context_header=chunk.context_header),
        )
    raise ValueError(f"no model prompt exists for chunk agent {chunk.agent!r}")


def _user_content(chunk: Chunk, instruction: str) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [{"type": "text", "text": instruction}]
    for page, image in zip(chunk.pages, chunk.images, strict=True):
        content.append({"type": "text", "text": f"Mutlak sayfa {page}"})
        encoded = base64.b64encode(image).decode("ascii")
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{encoded}",
                    "detail": VISION_DETAIL,
                },
            }
        )
    return content


def _parse_output(chunk: Chunk, raw: str) -> AgentOutput:
    payload = json.loads(_strip_code_fence(raw))
    model: type[BaseModel]
    if chunk.agent == ExtractorAgent.APPOINTMENTS:
        model = AppointmentsAgentOutput
    elif chunk.agent in {ExtractorAgent.RULES, ExtractorAgent.ANNEX}:
        model = RulesAgentOutput
    elif chunk.agent == ExtractorAgent.SPECIMENS:
        model = SpecimensAgentOutput
    else:
        raise ValueError(f"no output schema exists for chunk agent {chunk.agent!r}")
    return model.model_validate(payload)  # type: ignore[return-value]


def _strip_code_fence(raw: str) -> str:
    text = raw.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _describe_error(error: Exception) -> str:
    if isinstance(error, ValidationError):
        return str(error)
    if isinstance(error, json.JSONDecodeError):
        return f"invalid JSON: {error.msg} at line {error.lineno} column {error.colno}"
    return f"{type(error).__name__}: {error}"


def _success_detail(output: AgentOutput) -> str:
    if isinstance(output, AppointmentsAgentOutput):
        return f"{len(output.appointments)} appointments"
    if isinstance(output, RulesAgentOutput):
        return f"{len(output.rules)} rules"
    return f"{len(output.specimens)} specimens"


def _resolve_primary_model(value: str | None) -> str:
    model = value if value is not None else os.getenv("EXTRACTION_MODEL", "")
    model = model.strip()
    if not model:
        raise ExtractorConfigurationError("EXTRACTION_MODEL is required")
    return model


def _resolve_witness_model(value: str | None) -> str:
    model = value if value is not None else os.getenv("WITNESS_MODEL", "")
    return model.strip()


def _resolve_max_concurrency(value: int | None) -> int:
    if value is not None:
        if value < 1:
            raise ExtractorConfigurationError("max_concurrency must be at least 1")
        return value
    raw = os.getenv("MAX_CONCURRENCY", str(DEFAULT_MAX_CONCURRENCY))
    try:
        parsed = int(raw)
    except ValueError as error:
        raise ExtractorConfigurationError("MAX_CONCURRENCY must be an integer") from error
    if parsed < 1:
        raise ExtractorConfigurationError("MAX_CONCURRENCY must be at least 1")
    return parsed


async def _default_caller(
    chunk: Chunk,
    role: ExtractorRole,
    model: str,
    system_prompt: str,
    user_content: list[dict[str, Any]],
) -> str:
    from openai import AsyncOpenAI

    client = AsyncOpenAI()
    response = await client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError(f"{role.value} extractor returned empty content for {chunk.chunk_id}")
    return content
