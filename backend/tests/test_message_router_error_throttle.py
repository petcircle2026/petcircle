import asyncio

from app.services import message_router


class DummyDB:
    def rollback(self):
        return None


def test_route_message_sends_error_once_per_inbound_message(monkeypatch):
    # Reset shared in-memory state for deterministic behavior.
    message_router._error_sent.clear()

    sent_messages = []

    async def fake_send_text_message(db, to, text):
        sent_messages.append((to, text))

    def raise_router_error(db, from_number):
        raise NameError("name 'display_name' is not defined")

    monkeypatch.setattr(message_router, "send_text_message", fake_send_text_message)
    monkeypatch.setattr(message_router, "get_or_create_user", raise_router_error)

    db = DummyDB()

    first_message = {
        "from_number": "919100000000",
        "type": "text",
        "text": "hi",
        "message_id": "wamid.1",
    }
    # Same message retried by webhook.
    first_message_retry = dict(first_message)

    second_message = {
        "from_number": "919100000000",
        "type": "text",
        "text": "hello again",
        "message_id": "wamid.2",
    }

    # First message failure should send one generic sorry reply.
    asyncio.run(message_router.route_message(db, first_message))
    assert len(sent_messages) == 1

    # Retry of same inbound message should not send again.
    asyncio.run(message_router.route_message(db, first_message_retry))
    assert len(sent_messages) == 1

    # New inbound message failure should send again once.
    asyncio.run(message_router.route_message(db, second_message))
    assert len(sent_messages) == 2
