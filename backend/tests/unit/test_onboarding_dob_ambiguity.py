from datetime import date
from types import SimpleNamespace

import pytest

from app.services import onboarding
from app.utils.date_utils import is_ambiguous_date_input, parse_date


class _FakeDB:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("jan 26", True),
        ("26 jan", True),
        ("January 2026", False),
        ("26 January 2024", False),
    ],
)
def test_is_ambiguous_date_input(raw, expected):
    assert is_ambiguous_date_input(raw) is expected


def test_parse_date_supports_day_month_two_digit_year():
    assert parse_date("26 jan 24") == date(2024, 1, 26)


@pytest.mark.anyio
async def test_step_dob_asks_for_confirmation_on_ambiguous_input(monkeypatch):
    db = _FakeDB()
    pet = SimpleNamespace(name="Buddy", dob=None)
    user = SimpleNamespace(id="u1", onboarding_state="awaiting_dob", _plaintext_mobile="911234567890")

    monkeypatch.setattr(onboarding, "_get_pending_pet", lambda _db, _uid: pet)

    async def _fake_parse_date_with_ai(_text):
        return date(2026, 1, 1)

    monkeypatch.setattr(onboarding, "parse_date_with_ai", _fake_parse_date_with_ai)

    sent_messages = []

    async def _send_fn(_db, _to, text):
        sent_messages.append(text)

    await onboarding._step_dob(db, user, "jan 26", _send_fn)

    assert pet.dob == date(2026, 1, 1)
    assert user.onboarding_state == "awaiting_dob_confirm"
    assert db.commits == 1
    assert sent_messages
    assert "interpreted" in sent_messages[0].lower()
    assert "yes" in sent_messages[0].lower()


@pytest.mark.anyio
async def test_step_dob_confirm_yes_advances_to_weight(monkeypatch):
    db = _FakeDB()
    pet = SimpleNamespace(name="Buddy", dob=date(2026, 1, 1))
    user = SimpleNamespace(id="u1", onboarding_state="awaiting_dob_confirm", _plaintext_mobile="911234567890")

    monkeypatch.setattr(onboarding, "_get_pending_pet", lambda _db, _uid: pet)

    sent_messages = []

    async def _send_fn(_db, _to, text):
        sent_messages.append(text)

    await onboarding._step_dob_confirm(db, user, "yes", _send_fn)

    assert pet.dob == date(2026, 1, 1)
    assert user.onboarding_state == "awaiting_weight"
    assert db.commits == 1
    assert sent_messages
    assert "weight" in sent_messages[0].lower()
