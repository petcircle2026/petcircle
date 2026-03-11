from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.shown_fun_fact import ShownFunFact
from app.utils import breed_fun_facts


class FakeQuery:
    def __init__(self, db, entity):
        self.db = db
        self.entity = entity

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        if self.entity is ShownFunFact.fact_hash:
            return [SimpleNamespace(fact_hash=fact_hash) for fact_hash in self.db.shown_hashes]
        return []

    def delete(self, synchronize_session=None):
        self.db.shown_hashes.clear()
        return 0


class FakeSession:
    def __init__(self, shown_hashes=None):
        self.shown_hashes = list(shown_hashes or [])
        self._pending = []

    def query(self, entity):
        return FakeQuery(self, entity)

    def add(self, obj):
        self._pending.append(obj)

    def commit(self):
        for obj in self._pending:
            self.shown_hashes.append(obj.fact_hash)
        self._pending.clear()

    def rollback(self):
        self._pending.clear()


@pytest.mark.asyncio
async def test_returns_different_facts_for_back_to_back_messages(monkeypatch) -> None:
    db = FakeSession()
    user_id = uuid4()

    monkeypatch.setattr(breed_fun_facts.random, "choice", lambda facts: facts[0])

    first_fact = await breed_fun_facts.get_breed_fun_fact(db, user_id, "Labrador Retriever", "dog")
    second_fact = await breed_fun_facts.get_breed_fun_fact(db, user_id, "Labrador Retriever", "dog")

    assert first_fact != second_fact


@pytest.mark.asyncio
async def test_generates_new_fact_before_repeating_exhausted_pool(monkeypatch) -> None:
    user_id = uuid4()
    exhausted_hashes = [
        breed_fun_facts._hash_fact(fact)
        for fact in breed_fun_facts._DOG_FACTS["Labrador Retriever"]
    ]
    db = FakeSession(shown_hashes=exhausted_hashes)

    async def fake_generate_additional_fun_facts_with_ai(breed, species, excluded_facts, count=5):
        assert breed == "Labrador Retriever"
        assert species == "dog"
        assert excluded_facts == breed_fun_facts._DOG_FACTS["Labrador Retriever"]
        return ["Labs have an oily outer coat that helps icy water roll right off."]

    monkeypatch.setattr(breed_fun_facts.random, "choice", lambda facts: facts[0])
    monkeypatch.setattr(
        breed_fun_facts,
        "_generate_additional_fun_facts_with_ai",
        fake_generate_additional_fun_facts_with_ai,
    )

    fact = await breed_fun_facts.get_breed_fun_fact(db, user_id, "Labrador Retriever", "dog")

    assert fact == "Labs have an oily outer coat that helps icy water roll right off."
    assert breed_fun_facts._hash_fact(fact) in db.shown_hashes