"""Deterministic offline provider for tests and zero-credential development."""

from __future__ import annotations

from .base import AIProvider, ChatResponse, Message


class MockProvider(AIProvider):
    name = "mock"

    def generate(self, messages: list[Message], system_prompt: str | None = None) -> ChatResponse:
        user_messages = [message["content"] for message in messages if message.get("role") == "user"]
        if not user_messages:
            return ChatResponse("Send a message to start an offline test conversation.", "mock-1")
        latest = user_messages[-1].strip()
        memory_lines = []
        if system_prompt and "Relevant memories:" in system_prompt:
            memory_lines = [
                line[2:].strip()
                for line in system_prompt.splitlines()
                if line.startswith("- ") and "Relevant memories:" not in line
            ]
        answer = f'Offline mock response: I received "{latest[:500]}".'
        if memory_lines:
            answer += "\n\nRetrieved memory:\n" + "\n".join(f"- {item}" for item in memory_lines)
        answer += "\n\nNo external AI request was made. Select a configured provider for a model-generated answer."
        return ChatResponse(answer, "mock-1", {"input_messages": len(messages)})
