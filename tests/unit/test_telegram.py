import httpx
import pytest

from app.reports.telegram import (
    TELEGRAM_MAX_MESSAGE_LENGTH,
    TelegramNotificationError,
    TelegramNotifier,
)


class _FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error", request=httpx.Request("POST", "http://x"), response=self
            )

    def json(self):
        return self._json_data


def test_send_message_posts_to_telegram_api(monkeypatch):
    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append((url, json))
        return _FakeResponse({"ok": True})

    monkeypatch.setattr(httpx, "post", fake_post)
    notifier = TelegramNotifier(bot_token="tok", chat_id="123")

    notifier.send_message("hello")

    assert len(calls) == 1
    url, payload = calls[0]
    assert url == "https://api.telegram.org/bottok/sendMessage"
    assert payload["chat_id"] == "123"
    assert payload["text"] == "hello"


def test_send_message_raises_on_http_error(monkeypatch):
    monkeypatch.setattr(
        httpx, "post", lambda *a, **k: _FakeResponse({}, status_code=500)
    )
    notifier = TelegramNotifier(bot_token="tok", chat_id="123")

    with pytest.raises(TelegramNotificationError):
        notifier.send_message("hello")


def test_send_message_raises_when_api_returns_not_ok(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *a, **k: _FakeResponse({"ok": False, "description": "bad"}),
    )
    notifier = TelegramNotifier(bot_token="tok", chat_id="123")

    with pytest.raises(TelegramNotificationError):
        notifier.send_message("hello")


def test_requires_bot_token_and_chat_id():
    with pytest.raises(ValueError):
        TelegramNotifier(bot_token="", chat_id="123")
    with pytest.raises(ValueError):
        TelegramNotifier(bot_token="tok", chat_id="")


def test_long_message_is_split_into_multiple_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *a, json=None, **k: (calls.append(json), _FakeResponse({"ok": True}))[1],
    )
    notifier = TelegramNotifier(bot_token="tok", chat_id="123")

    long_text = "\n".join(f"line {i}" for i in range(1000))
    assert len(long_text) > TELEGRAM_MAX_MESSAGE_LENGTH

    notifier.send_message(long_text)

    assert len(calls) > 1
    for payload in calls:
        assert len(payload["text"]) <= TELEGRAM_MAX_MESSAGE_LENGTH
    # nothing lost across the chunk boundaries
    assert "\n".join(payload["text"] for payload in calls) == long_text


def test_chunk_keeps_short_text_as_single_chunk():
    assert TelegramNotifier._chunk("short message") == ["short message"]
