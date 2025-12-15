from __future__ import annotations

from aiogram import Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from app.bot.keyboards.main import build_main_keyboard
from app.services.billing import BillingService

START_INSTRUCTION = (
    "Добро пожаловать в Telegram-сервис генерации и обработки изображений.\n\n"
    "<a href=\"https://disk.yandex.ru/i/iMl_AwcVqTATDQ\">Договор оферты</a>\n"
    "<a href=\"https://disk.yandex.ru/i/ggsNkifolWTeXg\">Политика конфиденциальности</a>\n\n"
    "Нажимая «Start» и продолжая использовать Telegram-сервис, вы подтверждаете, что:\n"
    "– ознакомились и принимаете условия Договора публичной оферты на оказание услуг;\n"
    "– ознакомились с Политикой конфиденциальности и даёте согласие на обработку своих персональных данных в соответствии с законодательством РФ;\n"
    "– можете связаться с Исполнителем по вопросам сервиса и персональных данных по адресу general@digital-base.ru."
)

INFO_INSTRUCTION = (
    "Привет, выберите режим, нажмите кнопку:\n\n"
    "🎨 Создать — генерация изображений\n"
    "✍️ Написать — генерация промпта для создания изображения\n"
    "✏️ Изменить — умное редактирование изображений (добавление объектов, объединение, изменение)\n"
    "✨ Ретушь — деликатная ретушь лица\n"
    "📝 Добавить текст — добавление текста на изображение\n"
    "🔄 Заменить лицо — замена лица на фотографии\n"
    "⬆️ Улучшить — улучшение качества изображения (Upscale)\n"
    "💰 Баланс — просмотр баланса и пополнение\n\n"
    "🆘 Помощь — ИИ-помощник и связь с разработчиками\n"
    "ℹ️ Info — информация о функциях бота и сброс текущих процессов\n\n"
    "⚠️ **Важно:** Если происходит задержка ответа или возникает ошибка, нажмите кнопку «ℹ️ Info» для сброса сессии и повторите попытку заново.\n"
)


async def cmd_start(message: types.Message, state: FSMContext) -> None:
    await state.clear()
    
    # Check if this is a payment return
    if message.text and message.text.startswith("/start payment_"):
        payment_param = message.text.split("payment_")[-1] if "payment_" in message.text else None
        if payment_param:
            # Check payment status from YooKassa
            from app.services.payment import PaymentService
            from app.db.base import SessionLocal
            from app.db.models import Payment
            import json
            
            db = SessionLocal()
            try:
                # Try to find payment by return_payment_id from metadata, or by yookassa_payment_id
                payment = None
                
                # First, try to find by return_payment_id (UUID from return_url)
                all_payments = db.query(Payment).filter(
                    Payment.raw_data.isnot(None)
                ).all()
                for p in all_payments:
                    if p.raw_data and isinstance(p.raw_data, dict):
                        metadata = p.raw_data.get("metadata", {})
                        if metadata.get("return_payment_id") == payment_param:
                            payment = p
                            break
                
                # If not found, try by yookassa_payment_id (in case return_url has yookassa ID)
                if not payment:
                    payment = db.query(Payment).filter(Payment.yookassa_payment_id == payment_param).first()
                
                # If still not found, try by numeric ID
                if not payment and payment_param.isdigit():
                    payment = db.query(Payment).filter(Payment.id == int(payment_param)).first()
                
                if payment and payment.yookassa_payment_id:
                    # Check status from YooKassa API
                    status_info = PaymentService.check_payment_status_from_yookassa(
                        db, payment.yookassa_payment_id
                    )
                    if status_info:
                        if status_info["status"] == "succeeded" and status_info["paid"]:
                            balance_after = BillingService.get_user_balance(db, payment.user_id)
                            balance_after_rubles = balance_after / 100.0
                            if status_info.get("credited", False):
                                text = (
                                    "✅ **Оплата успешно подтверждена!**\n\n"
                                    f"💰 Ваш баланс пополнен на {status_info['amount']:.2f}₽\n"
                                    f"💵 Текущий баланс: {balance_after_rubles:.2f}₽"
                                )
                            else:
                                text = (
                                    "ℹ️ **Оплата уже была зачислена ранее.**\n\n"
                                    f"💵 Текущий баланс: {balance_after_rubles:.2f}₽"
                                )
                            await message.answer(
                                text,
                                reply_markup=build_main_keyboard(),
                                parse_mode="Markdown"
                            )
                        elif status_info["status"] == "pending":
                            await message.answer(
                                "⏳ **Платеж обрабатывается...**\n\n"
                                "Пожалуйста, подождите несколько секунд и проверьте баланс.",
                                reply_markup=build_main_keyboard(),
                                parse_mode="Markdown"
                            )
                        else:
                            await message.answer(
                                "❌ **Платеж не завершен**\n\n"
                                "Если вы оплатили, но баланс не пополнился, обратитесь в поддержку.",
                                reply_markup=build_main_keyboard(),
                                parse_mode="Markdown"
                            )
                    else:
                        await message.answer(
                            "⚠️ **Не удалось проверить статус платежа**\n\n"
                            "Проверьте баланс через кнопку '💰 Баланс'",
                            reply_markup=build_main_keyboard(),
                            parse_mode="Markdown"
                        )
                else:
                    await message.answer(
                        START_INSTRUCTION,
                        reply_markup=build_main_keyboard(),
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
            except Exception as e:
                from loguru import logger
                logger.error(f"Error checking payment status: {e}", exc_info=True)
                await message.answer(
                    START_INSTRUCTION,
                    reply_markup=build_main_keyboard(),
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
            finally:
                db.close()
            return
    
    await message.answer(
        START_INSTRUCTION,
        reply_markup=build_main_keyboard(),
        parse_mode="HTML",
        disable_web_page_preview=True
    )


def register_start_handlers(dp: Dispatcher) -> None:
    dp.message.register(cmd_start, Command("start"))

