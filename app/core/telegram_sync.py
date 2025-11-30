from __future__ import annotations

import json
import threading
from typing import Any

import requests
from loguru import logger

from app.core.config import settings

# Global requests session for Telegram API with connection pooling
_telegram_session: requests.Session | None = None
_telegram_session_lock = threading.Lock()
TELEGRAM_API_BASE = "https://api.telegram.org/bot"


def _get_telegram_session() -> requests.Session:
    """Get or create global requests session for Telegram API."""
    global _telegram_session
    if _telegram_session is None:
        with _telegram_session_lock:
            if _telegram_session is None:
                _telegram_session = requests.Session()
                _telegram_session.headers.update({
                    'User-Agent': 'MediaBot/1.0',
                    'Connection': 'keep-alive'
                })
                # Connection pooling settings
                adapter = requests.adapters.HTTPAdapter(
                    pool_connections=10,
                    pool_maxsize=20,
                    max_retries=3,
                    pool_block=False
                )
                _telegram_session.mount('https://', adapter)
                _telegram_session.mount('http://', adapter)
    return _telegram_session


def send_message_sync(
    chat_id: int,
    text: str,
    reply_to_message_id: int | None = None,
    message_thread_id: int | None = None,
) -> bool:
    """Send text message synchronously via Telegram Bot API."""
    session = _get_telegram_session()
    url = f"{TELEGRAM_API_BASE}{settings.tg_bot_token}/sendMessage"
    
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
    }
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    if message_thread_id:
        payload["message_thread_id"] = message_thread_id
    
    try:
        response = session.post(url, json=payload, timeout=10.0)
        response.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to send Telegram message: {}", exc)
        return False


def send_document_sync(
    chat_id: int,
    document: str | bytes,
    filename: str | None = None,
    caption: str | None = None,
    reply_to_message_id: int | None = None,
    message_thread_id: int | None = None,
    reply_markup: dict[str, Any] | None = None,
) -> int | None:
    """Send document synchronously via Telegram Bot API.
    
    Args:
        document: URL string or bytes content
        filename: Required if document is bytes
    
    Returns:
        message_id of sent message, or None if failed
    """
    session = _get_telegram_session()
    url = f"{TELEGRAM_API_BASE}{settings.tg_bot_token}/sendDocument"
    
    payload: dict[str, Any] = {
        "chat_id": chat_id,
    }
    if caption:
        # Не обрезаем caption здесь - это делается в вызывающем коде
        # Telegram limit: 1024 characters (проверяется в вызывающем коде)
        payload["caption"] = caption
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    if message_thread_id:
        payload["message_thread_id"] = message_thread_id
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    
    files = None
    if isinstance(document, bytes):
        # Send as file upload
        if not filename:
            filename = "file.png"
        files = {"document": (filename, document, "application/octet-stream")}
        try:
            logger.info("Sending document to Telegram: chat_id={}, filename={}, size={} bytes, caption_length={}", 
                       chat_id, filename, len(document), len(caption) if caption else 0)
            response = session.post(url, data=payload, files=files, timeout=120.0)  # Увеличиваем таймаут до 2 минут
            response.raise_for_status()
            result = response.json()
            if result.get("ok") and result.get("result"):
                message_id = result["result"].get("message_id")
                logger.info("Successfully sent document to Telegram: message_id={}, chat_id={}", message_id, chat_id)
                return message_id
            else:
                logger.error("Telegram API returned error: {}", result)
                return None
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to send Telegram document (bytes): {}", exc, exc_info=True)
            return None
    else:
        # Send as URL
        payload["document"] = document
        try:
            logger.info("Sending document URL to Telegram: chat_id={}, url={}, caption_length={}", 
                       chat_id, document[:100] if isinstance(document, str) else "N/A", len(caption) if caption else 0)
            response = session.post(url, json=payload, timeout=120.0)  # Увеличиваем таймаут до 2 минут
            response.raise_for_status()
            result = response.json()
            if result.get("ok") and result.get("result"):
                message_id = result["result"].get("message_id")
                logger.info("Successfully sent document URL to Telegram: message_id={}, chat_id={}", message_id, chat_id)
                return message_id
            else:
                logger.error("Telegram API returned error: {}", result)
                return None
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to send Telegram document (URL): {}", exc, exc_info=True)
            return None



