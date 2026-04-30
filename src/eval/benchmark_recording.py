"""Response recording helpers for benchmark model calls."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any


@dataclass(slots=True)
class BenchmarkResponseRecorder:
    last_raw_output: str | None = None

    def reset(self) -> None:
        self.last_raw_output = None

    def capture_response(self, response: Any) -> None:
        choices = getattr(response, "choices", None)
        if not isinstance(choices, list) or not choices:
            return
        message = getattr(choices[0], "message", None)
        raw_content = getattr(message, "content", None)
        if isinstance(raw_content, str) and raw_content.strip():
            self.last_raw_output = raw_content


class RecordingChatCompletions:
    def __init__(self, *, wrapped: Any, recorder: BenchmarkResponseRecorder) -> None:
        self._wrapped = wrapped
        self._recorder = recorder

    async def create(self, **kwargs: Any) -> Any:
        response = await self._wrapped.create(**kwargs)
        self._recorder.capture_response(response)
        return response


def wrap_client_with_recorder(
    *,
    client: Any,
    recorder: BenchmarkResponseRecorder,
) -> Any:
    chat = getattr(client, "chat", None)
    completions = getattr(chat, "completions", None)
    if completions is None or not hasattr(completions, "create"):
        return client
    return SimpleNamespace(
        chat=SimpleNamespace(
            completions=RecordingChatCompletions(wrapped=completions, recorder=recorder)
        )
    )


def extract_stage_raw_output(*, recorder: BenchmarkResponseRecorder, subject: Any) -> str | None:
    if recorder.last_raw_output:
        return recorder.last_raw_output
    raw_output = getattr(subject, "_benchmark_last_raw_output", None)
    return raw_output if isinstance(raw_output, str) and raw_output.strip() else None
