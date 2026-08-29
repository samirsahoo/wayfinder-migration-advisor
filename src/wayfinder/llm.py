"""Pluggable narrative-generation layer.

Every agent's *analysis* (the readiness score, the risk list, the cost tier)
is produced by deterministic, inspectable heuristics in ``agents/*.py`` --
that logic never depends on an LLM being available, so the graph is fully
testable offline and free to run.

An LLM is used for exactly one thing: turning that structured analysis into
readable prose (the ``summary`` fields). This module is the seam between the
two. ``MockNarrator`` is the default and needs no API key or network access.
Set ``WAYFINDER_LLM_PROVIDER=anthropic`` (plus ``ANTHROPIC_API_KEY``) to swap
in a real model without touching any agent code.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod


class Narrator(ABC):
    """Turns a short structured brief into a couple of sentences of prose."""

    @abstractmethod
    def narrate(self, *, role: str, brief: str) -> str:
        """``role`` is the agent's persona (e.g. "cloud architecture
        advisor"); ``brief`` is a compact, factual bullet list the narrator
        must not contradict -- it may only phrase it for a human reader."""


class MockNarrator(Narrator):
    """Deterministic, offline, zero-dependency narrator.

    Templates the brief into a short paragraph. This is what Wayfinder uses
    out of the box so `wayfinder run examples/*.yaml` works immediately on a
    clean checkout with no API key -- important for a portfolio piece that
    strangers will actually clone and run.
    """

    def narrate(self, *, role: str, brief: str) -> str:
        lines = [ln.strip("- ").strip() for ln in brief.strip().splitlines() if ln.strip()]
        if not lines:
            return f"The {role} found nothing notable to report."
        if len(lines) == 1:
            body = lines[0]
        else:
            body = "; ".join(lines[:-1]) + f"; and {lines[-1]}"
        return f"As {role}, the assessment is: {body}."


class AnthropicNarrator(Narrator):
    """Real LLM narration via the Anthropic Messages API.

    Kept intentionally thin: same contract as MockNarrator, so swapping the
    provider never touches agent logic. Requires the ``anthropic`` package
    and ``ANTHROPIC_API_KEY`` in the environment.
    """

    def __init__(self, model: str = "claude-sonnet-4-5") -> None:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - exercised only when selected
            raise RuntimeError(
                "AnthropicNarrator requires the 'anthropic' package: pip install anthropic"
            ) from exc
        self._client = anthropic.Anthropic()
        self._model = model

    def narrate(self, *, role: str, brief: str) -> str:
        message = self._client.messages.create(
            model=self._model,
            max_tokens=220,
            system=(
                f"You are the {role} inside an automated cloud-migration advisory system. "
                "Rewrite the analyst's brief below as 2-4 crisp sentences for a CTO audience. "
                "Do not invent facts, numbers, or risks that are not already in the brief."
            ),
            messages=[{"role": "user", "content": brief}],
        )
        return "".join(block.text for block in message.content if block.type == "text").strip()


def get_narrator() -> Narrator:
    """Provider selection, driven entirely by environment variables so the
    CLI and the graph never need to know which provider is active."""

    provider = os.environ.get("WAYFINDER_LLM_PROVIDER", "mock").lower()
    if provider == "anthropic":
        return AnthropicNarrator(model=os.environ.get("WAYFINDER_LLM_MODEL", "claude-sonnet-4-5"))
    if provider == "mock":
        return MockNarrator()
    raise ValueError(f"Unknown WAYFINDER_LLM_PROVIDER={provider!r} (expected 'mock' or 'anthropic')")
