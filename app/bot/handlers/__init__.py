from aiogram import Dispatcher

from .face_swap import register_face_swap_handlers
from .image import register_image_handlers
from .ping import register_ping_handlers
from .menu import register_menu_handlers
from .start import register_start_handlers
from .status import register_status_handlers
from .stylish_text import register_stylish_text_handlers
from .prompt_writer import register_prompt_writer_handlers
from .billing import register_billing_handlers
from .help import register_help_handlers


def setup_handlers(dp: Dispatcher) -> None:
    register_start_handlers(dp)
    register_menu_handlers(dp)
    register_help_handlers(dp)  # Регистрируем помощь после меню
    register_ping_handlers(dp)
    register_face_swap_handlers(dp)
    # Регистрируем биллинг ПЕРЕД image handlers
    # В aiogram обработчики проверяются в обратном порядке (последний = первый)
    # Но router'ы проверяются в порядке регистрации, поэтому billing router должен быть зарегистрирован ПОСЛЕ image router
    # чтобы его обработчики проверялись ПЕРВЫМИ
    register_billing_handlers(dp)  # Регистрируем биллинг для команд /balance и промокодов
    # Регистрируем Stylish text ПЕРЕД image handlers, чтобы иметь приоритет
    register_stylish_text_handlers(dp)
    register_image_handlers(dp)  # Внутри регистрируется обработчик кнопки "Написать"
    # Регистрируем обработчик текста после показа меню баланса ПОСЛЕ image handlers
    # чтобы он проверялся ПЕРВЫМ (в aiogram обработчики проверяются в обратном порядке)
    from .billing import handle_text_after_balance_menu, PaymentStates
    from aiogram import F
    from aiogram.filters import StateFilter
    
    dp.message.register(
        handle_text_after_balance_menu,
        StateFilter(PaymentStates.BALANCE_MENU_SHOWN),
        F.text
    )
    # ВАЖНО: Регистрируем обработчик состояния prompt_writer ПОСЛЕ image handlers,
    # чтобы он проверялся ПЕРВЫМ (в aiogram обработчики проверяются в обратном порядке регистрации)
    # Обработчик с фильтром состояния имеет приоритет над общим обработчиком текста
    register_prompt_writer_handlers(dp)
    register_status_handlers(dp)

