# ai/main.py
"""Exposes health, extraction, and comparison endpoints for the AI service."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import ValidationError

if __package__:
    from .compare import analyze, degraded_report
    from .schema import AnalyzeRequest, CheckReport, HealthResponse
else:
    from compare import analyze, degraded_report
    from schema import AnalyzeRequest, CheckReport, HealthResponse


load_dotenv(Path(__file__).with_name(".env"))

app = FastAPI(
    title="YetkiCheck AI Service",
    version="1.0.0",
    description="Stateless extraction and deterministic document comparison service.",
)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Reports readiness without exposing credentials or mutable service state."""

    engine = os.getenv("EXTRACTION_MODEL") or "unconfigured"
    return HealthResponse(engine=engine)


@app.post("/analyze", response_model=CheckReport)
async def analyze_application(payload: dict[str, Any]) -> CheckReport:
    """Compares an application against its document and the registry — deterministic, no model."""

    try:
        request = AnalyzeRequest.model_validate(payload)
    except ValidationError as error:
        # A malformed body still gets nine red rows: the review screen never loses its checklist.
        return degraded_report(error)
    return analyze(request)

