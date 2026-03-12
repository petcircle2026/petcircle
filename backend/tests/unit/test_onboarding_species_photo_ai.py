from types import SimpleNamespace

import pytest

from app.services import onboarding


class _FakeDB:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


@pytest.mark.anyio
async def test_step_pet_photo_uses_ai_and_asks_confirmation(monkeypatch):
    db = _FakeDB()
    pet = SimpleNamespace(id="p1", name="Buddy", photo_path=None, species="_pending")
    user = SimpleNamespace(id="u1", onboarding_state="awaiting_pet_photo", _plaintext_mobile="911234567890")

    monkeypatch.setattr(onboarding, "_get_pending_pet", lambda _db, _uid: pet)

    async def _fake_download(_media_id):
        return (b"fake-image", "image/jpeg")

    async def _fake_upload(_bytes, _path, _mime):
        return None

    async def _fake_ai(_bytes, _mime):
        return {"species": "dog", "breed": "Labrador Retriever"}

    monkeypatch.setattr("app.services.whatsapp_sender.download_whatsapp_media", _fake_download)
    monkeypatch.setattr("app.services.document_upload.upload_to_supabase", _fake_upload)
    monkeypatch.setattr(onboarding, "_ai_identify_pet_from_photo", _fake_ai)

    sent_messages = []

    async def _send_fn(_db, _to, text):
        sent_messages.append(text)

    await onboarding._step_pet_photo(
        db,
        user,
        "",
        _send_fn,
        message_data={"type": "image", "media_id": "m1"},
    )

    assert user.onboarding_state == "awaiting_species_confirm"
    assert pet.species == "dog"
    assert pet.breed == "Labrador Retriever"
    assert pet.photo_path is not None
    assert sent_messages
    assert "i think" in sent_messages[0].lower()
    assert "yes" in sent_messages[0].lower()


@pytest.mark.anyio
async def test_step_pet_photo_ai_unknown_falls_back_to_manual_species(monkeypatch):
    db = _FakeDB()
    pet = SimpleNamespace(id="p1", name="Milo", photo_path=None, species="_pending")
    user = SimpleNamespace(id="u1", onboarding_state="awaiting_pet_photo", _plaintext_mobile="911234567890")

    monkeypatch.setattr(onboarding, "_get_pending_pet", lambda _db, _uid: pet)

    async def _fake_download(_media_id):
        return (b"fake-image", "image/jpeg")

    async def _fake_upload(_bytes, _path, _mime):
        return None

    async def _fake_ai(_bytes, _mime):
        return {"species": None, "breed": None}

    monkeypatch.setattr("app.services.whatsapp_sender.download_whatsapp_media", _fake_download)
    monkeypatch.setattr("app.services.document_upload.upload_to_supabase", _fake_upload)
    monkeypatch.setattr(onboarding, "_ai_identify_pet_from_photo", _fake_ai)

    sent_messages = []

    async def _send_fn(_db, _to, text):
        sent_messages.append(text)

    await onboarding._step_pet_photo(
        db,
        user,
        "",
        _send_fn,
        message_data={"type": "image", "media_id": "m1"},
    )

    assert user.onboarding_state == "awaiting_species"
    assert pet.species == "_pending"
    assert sent_messages
    assert "dog" in sent_messages[0].lower()
    assert "cat" in sent_messages[0].lower()


@pytest.mark.anyio
async def test_step_pet_photo_skip_asks_species(monkeypatch):
    db = _FakeDB()
    pet = SimpleNamespace(id="p1", name="Milo", photo_path=None, species="_pending")
    user = SimpleNamespace(id="u1", onboarding_state="awaiting_pet_photo", _plaintext_mobile="911234567890")

    monkeypatch.setattr(onboarding, "_get_pending_pet", lambda _db, _uid: pet)

    sent_messages = []

    async def _send_fn(_db, _to, text):
        sent_messages.append(text)

    await onboarding._step_pet_photo(db, user, "skip", _send_fn, message_data={"type": "text"})

    assert user.onboarding_state == "awaiting_species"
    assert sent_messages
    assert "dog" in sent_messages[0].lower()
    assert "cat" in sent_messages[0].lower()


@pytest.mark.anyio
async def test_step_species_confirm_accepts_yes(monkeypatch):
    db = _FakeDB()
    pet = SimpleNamespace(id="p1", name="Buddy", species="cat", breed="Persian")
    user = SimpleNamespace(id="u1", onboarding_state="awaiting_species_confirm", _plaintext_mobile="911234567890")

    monkeypatch.setattr(onboarding, "_get_pending_pet", lambda _db, _uid: pet)

    sent_messages = []

    async def _send_fn(_db, _to, text):
        sent_messages.append(text)

    await onboarding._step_species_confirm(db, user, "yes", _send_fn)

    assert user.onboarding_state == "awaiting_breed_confirm"
    assert pet.species == "cat"
    assert db.commits == 1
    assert sent_messages
    assert "breed" in sent_messages[0].lower()


@pytest.mark.anyio
async def test_step_breed_confirm_accepts_yes_and_moves_to_gender(monkeypatch):
    db = _FakeDB()
    pet = SimpleNamespace(id="p1", name="Buddy", species="dog", breed="Labrador")
    user = SimpleNamespace(id="u1", onboarding_state="awaiting_breed_confirm", _plaintext_mobile="911234567890")

    monkeypatch.setattr(onboarding, "_get_pending_pet", lambda _db, _uid: pet)

    sent_messages = []

    async def _send_fn(_db, _to, text):
        sent_messages.append(text)

    await onboarding._step_breed_confirm(db, user, "yes", _send_fn)

    assert user.onboarding_state == "awaiting_gender"
    assert pet.breed == "Labrador"
    assert db.commits == 1
    assert sent_messages
    assert "gender" in sent_messages[0].lower()


@pytest.mark.anyio
async def test_step_breed_when_species_pending_asks_species(monkeypatch):
    db = _FakeDB()
    pet = SimpleNamespace(id="p1", name="Buddy", species="_pending", breed=None)
    user = SimpleNamespace(id="u1", onboarding_state="awaiting_breed", _plaintext_mobile="911234567890")

    monkeypatch.setattr(onboarding, "_get_pending_pet", lambda _db, _uid: pet)

    sent_messages = []

    async def _send_fn(_db, _to, text):
        sent_messages.append(text)

    await onboarding._step_breed(db, user, "labrador", _send_fn)

    assert user.onboarding_state == "awaiting_species"
    assert pet.breed is not None
    assert sent_messages
    assert "dog" in sent_messages[0].lower()
    assert "cat" in sent_messages[0].lower()
