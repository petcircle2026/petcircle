import json
from datetime import date

import pytest

from app.services import onboarding


class _FakeChatCompletions:
    async def create(self, **kwargs):
        content = json.dumps(
            {
                "reasonable": True,
                "expected_range": "8-14 kg",
                "reason": "Breed and age are consistent with entered weight.",
            }
        )

        class _Message:
            def __init__(self, c):
                self.content = c

        class _Choice:
            def __init__(self, c):
                self.message = _Message(c)

        class _Resp:
            def __init__(self, c):
                self.choices = [_Choice(c)]

        return _Resp(content)


class _FakeClientNoResponses:
    def __init__(self):
        self.chat = type("_Chat", (), {"completions": _FakeChatCompletions()})()


@pytest.mark.anyio
async def test_ai_check_weight_falls_back_to_chat_completions(monkeypatch):
    monkeypatch.setattr(onboarding.settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        onboarding,
        "_get_openai_onboarding_client",
        lambda: _FakeClientNoResponses(),
    )

    async def _retry_passthrough(func, *args, **kwargs):
        return await func(*args, **kwargs)

    monkeypatch.setattr(onboarding, "retry_openai_call", _retry_passthrough)

    result = await onboarding._ai_check_weight(
        species="dog",
        breed="beagle",
        dob=date(2022, 1, 1),
        weight_kg=10.5,
    )

    assert result is not None
    assert result["reasonable"] is True
    assert result["expected_range"] == "8-14 kg"
