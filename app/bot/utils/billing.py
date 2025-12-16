"""Shared helpers for billing-related bot messages."""
from __future__ import annotations

from aiogram import types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from loguru import logger

from app.utils.money import format_kopecks, kopecks_to_rubles


async def handle_charge_failure_message(
    message: types.Message,
    *,
    price: float,
    balance_kopecks: int | float | None,
    error_msg: str | None,
    cost_caption: str,
    log_prefix: str,
) -> bool:
    """
    Notify user about insufficient balance or raise on other billing errors.

    Returns:
        bool: True if user was notified about insufficient balance, False otherwise.
    """
    balance_rub = kopecks_to_rubles(balance_kopecks)
    balance_text = format_kopecks(balance_kopecks)
    error_text = (error_msg or "").lower()

    if "insufficient balance" in error_text:
        text = (
            f"❌ **Недостаточно средств**\n\n"
            f"{cost_caption}: {price} ₽\n"
            f"Ваш баланс: {balance_text} ₽\n\n"
            f"Пополните баланс для продолжения работы."
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="💰 Пополнить баланс",
                        callback_data="payment_menu",
                    )
                ]
            ]
        )
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
        logger.info(
            "{}: insufficient balance detected, notified user (price={}₽, balance={}₽)",
            log_prefix,
            price,
            balance_rub,
        )
        return True

    logger.error(
        "{}: failed to reserve operation (error_msg={!r})",
        log_prefix,
        error_msg,
    )
    raise RuntimeError(error_msg or f"{log_prefix}: failed to reserve operation")




