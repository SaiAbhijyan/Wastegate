"""Laya adapter (NandhaKishorM/laya, Apache-2.0): argument shapes only.

Live inference is DISABLED in session 1 (no install, no weights). Per Laya's README the base
checkpoints are near chance zero-shot and over-confident until temperature-fitted, so this
backend must not route real traffic before Phase 3 calibration on our labels.
"""
from __future__ import annotations

from typing import Any, Mapping

from .base import Answer, Question
from .jev import build_request, parse_response


def build_predict_args(state: str, questions: Mapping[str, Question]) -> tuple[str, dict[str, Any]]:
    """Args for laya.Router().predict(state, questions)."""
    return state, build_request(state, questions)["questions"]


def parse_predict(result: Mapping[str, Any], questions: Mapping[str, Question]):
    return parse_response(result, questions, backend="laya")


class LayaSystemOne:
    name = "laya"

    def __init__(self, temperature: float | None = None):
        self.temperature = temperature  # fitted in Phase 3; None = uncalibrated

    def decide(self, state: str, questions: Mapping[str, Question]) -> dict[str, Answer]:
        raise NotImplementedError("live Laya inference disabled in session 1")
