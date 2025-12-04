from __future__ import annotations

import asyncio

from aiogram import Dispatcher, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from loguru import logger

from app.bot.keyboards.main import (
    PROMPT_WRITER_BUTTON,
    CREATE_BUTTON,
    IMAGE_SMART_MERGE_BUTTON,
    IMAGE_RETOUCHER_BUTTON,
    IMAGE_STYLISH_TEXT_BUTTON,
    IMAGE_FACE_SWAP_BUTTON,
    IMAGE_UPSCALE_BUTTON,
    BALANCE_BUTTON,
    INFO_BUTTON,
    HELP_BUTTON,
    build_main_keyboard,
)
from app.providers.fal.llm import generate_prompt


class PromptWriterStates(StatesGroup):
    waiting_input = State()


async def handle_prompt_writer_start(message: types.Message, state: FSMContext) -> None:
    """Обработчик начала работы с кнопкой 'Написать'."""
    await state.set_state(PromptWriterStates.waiting_input)
    await message.answer(
        "✍️ ИИ ассистент поможет написать промпт на основе вашей идеи.\n\n"
        "Опишите, какое изображение вы хотите создать, и я сгенерирую детальный промпт для нейросети.\n\n"
        "💡 Пример: «Напиши портрет бизнес-леди в современном офисе, профессиональная фотография»",
        reply_markup=build_main_keyboard(),
    )


async def handle_prompt_writer_text(message: types.Message, state: FSMContext) -> None:
    """Обработчик текстового запроса для генерации промпта."""
    logger.info("handle_prompt_writer_text CALLED: text='{}', user_id={}", 
                message.text[:50] if message.text else None, 
                message.from_user.id if message.from_user else "unknown")
    if not message.text:
        logger.warning("handle_prompt_writer_text: no text in message")
        return
    
    # Проверяем, не является ли текст одной из кнопок главного меню
    # Если это кнопка, показываем сообщение о необходимости сбросить сессию или ввести промпт
    main_menu_buttons = {
        CREATE_BUTTON,
        PROMPT_WRITER_BUTTON,
        IMAGE_SMART_MERGE_BUTTON,
        IMAGE_RETOUCHER_BUTTON,
        IMAGE_STYLISH_TEXT_BUTTON,
        IMAGE_FACE_SWAP_BUTTON,
        IMAGE_UPSCALE_BUTTON,
        BALANCE_BUTTON,
        INFO_BUTTON,
        HELP_BUTTON,
    }
    
    if message.text in main_menu_buttons:
        logger.info("handle_prompt_writer_text: user pressed button '{}' while in prompt writer mode", message.text)
        await message.answer(
            "⚠️ Вы находитесь в режиме **«✍️ Написать»**.\n\n"
            "Для перехода в другой режим:\n"
            "• Нажмите кнопку **«ℹ️ Info»** для сброса текущей сессии\n"
            "• Затем выберите нужный режим\n\n"
            "Или введите текст промпта для генерации.",
            parse_mode="Markdown",
            reply_markup=build_main_keyboard(),
        )
        return
    
    # Проверка баланса перед генерацией промпта
    from app.services.billing import BillingService
    from app.services.pricing import get_operation_price
    from app.db.base import SessionLocal
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    db = SessionLocal()
    try:
        user_id = message.from_user.id if message.from_user else None
        if not user_id:
            await message.answer("Ошибка: не удалось определить пользователя.")
            await state.clear()
            return
        
        user, _ = BillingService.get_or_create_user(db, user_id, message.from_user)
        price = get_operation_price("prompt_generation")
        
        # Check for active discount code in state or database
        from app.bot.handlers.image import get_operation_discount_percent
        discount_percent = None
        if state:
            discount_percent = await get_operation_discount_percent(state, user_id)
        
        success, error_msg, operation_id = BillingService.charge_operation(
            db, user.id, "prompt_generation",
            discount_percent=discount_percent
        )
        
        if not success:
            balance_kopecks = BillingService.get_user_balance(db, user.id)
            balance_rub = balance_kopecks / 100.0
            text = (
                f"❌ **Недостаточно средств**\n\n"
                f"Генерация промпта стоит: {price} ₽\n"
                f"Ваш баланс: {balance_rub:.2f} ₽\n\n"
                f"Пополните баланс для продолжения работы."
            )
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="💰 Пополнить баланс",
                        callback_data="payment_menu"
                    )
                ]
            ])
            await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
            await state.clear()
            return
        
        logger.info("Prompt generation reserved: operation_id={}, price={}₽", operation_id, price)
    finally:
        db.close()
    
    try:
        await message.answer("Генерирую промпт...")
        generated_prompt = await asyncio.to_thread(generate_prompt, message.text)
        
        # Сохраняем сгенерированный промпт в состояние для использования в режиме создания
        await state.update_data(prompt=generated_prompt)
        
        # НЕ очищаем состояние - оставляем возможность продолжить диалог и уточнить промпт
        # Пользователь может продолжить общение или вернуться в главное меню для создания изображения
        # await state.set_state(None)  # Убрано - оставляем состояние для продолжения диалога
        
        await message.answer(
            f"✅ Промпт сгенерирован:\n```\n{generated_prompt}\n```\n\n"
            f"💡 Вы можете уточнить промпт, написав дополнительные детали, или вернуться в главное меню для создания изображения.",
            parse_mode="Markdown",
            reply_markup=build_main_keyboard(),
        )
        
        # Confirm operation after successful generation
        if operation_id:
            db = SessionLocal()
            try:
                success = BillingService.confirm_operation(db, operation_id)
                if success:
                    logger.info("Confirmed operation {} for prompt generation", operation_id)
                else:
                    logger.error("Failed to confirm operation {} for prompt generation", operation_id)
            except Exception as e:
                logger.error("Error confirming operation {} for prompt generation: {}", operation_id, e, exc_info=True)
            finally:
                db.close()
    except Exception as e:
        logger.error("Failed to generate prompt: {}", e, exc_info=True)
        # Mark operation as failed on error
        if operation_id:
            db = SessionLocal()
            try:
                BillingService.fail_operation(db, operation_id)
                logger.info("Marked operation {} as failed for prompt generation due to error", operation_id)
            except Exception as fail_error:
                logger.error("Error failing operation {} for prompt generation: {}", operation_id, fail_error, exc_info=True)
            finally:
                db.close()
        await message.answer("Не удалось сгенерировать промпт. Попробуйте еще раз.")
        await state.clear()  # Очищаем состояние только при ошибке


def register_prompt_writer_handlers(dp: Dispatcher) -> None:
    """Регистрирует обработчики для кнопки 'Написать'."""
    # Обработчик кнопки "Написать" регистрируется в register_image_handlers для правильного приоритета
    # Здесь регистрируем только обработчик состояния для генерации промпта
    # ВАЖНО: этот обработчик должен регистрироваться ПОСЛЕ handle_prompt_input, чтобы проверяться ПЕРВЫМ
    # (в aiogram обработчики проверяются в обратном порядке регистрации)
    logger.info("Registering handle_prompt_writer_text with state: {}", PromptWriterStates.waiting_input)
    dp.message.register(handle_prompt_writer_text, PromptWriterStates.waiting_input, F.text)
    logger.info("handle_prompt_writer_text registered successfully")

