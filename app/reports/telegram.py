import logging
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)

TELEGRAM_MAX_MESSAGE_LENGTH = 4096


class TelegramNotificationError(Exception):
    """Raised when a message fails to send. Callers must not let this break
    the run - a notification failure should never prevent the scan itself
    from completing and persisting its results (plan section 45).
    """


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str, timeout: float = 15.0):
        if not bot_token or not chat_id:
            raise ValueError("bot_token and chat_id are required")
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.timeout = timeout

    def send_message(self, text: str, parse_mode: Optional[str] = None) -> None:
        for chunk in self._chunk(text):
            self._send_single(chunk, parse_mode)

    def _send_single(self, text: str, parse_mode: Optional[str] = None) -> None:
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        try:
            response = httpx.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            if not data.get("ok", False):
                raise TelegramNotificationError(f"Telegram API returned not-ok: {data}")
        except httpx.HTTPError as e:
            raise TelegramNotificationError(f"Telegram request failed: {e}") from e

    @staticmethod
    def _chunk(text: str, max_length: int = TELEGRAM_MAX_MESSAGE_LENGTH) -> List[str]:
        if len(text) <= max_length:
            return [text]

        chunks: List[str] = []
        current = ""
        for line in text.split("\n"):
            candidate = f"{current}\n{line}" if current else line
            if len(candidate) > max_length:
                if current:
                    chunks.append(current)
                current = line
            else:
                current = candidate
        if current:
            chunks.append(current)
        return chunks
