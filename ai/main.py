# ai/main.py
"""Exposes health, extraction, and comparison endpoints for the AI service."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

if __package__:
    from .schema import HealthResponse
else:
    from schema import HealthResponse


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

