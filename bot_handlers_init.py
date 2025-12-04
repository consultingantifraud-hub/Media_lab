from aiogram import Dispatcher

from .face_swap import register_face_swap_handlers
from .image import register_image_handlers
from .ping import register_ping_handlers
from .menu import register_menu_handlers
from .start import register_start_handlers
from .status import register_status_handlers
from .stylish_text import register_stylish_text_handlers


def setup_handlers(dp: Dispatcher) -> None:
    register_start_handlers(dp)
    register_menu_handlers(dp)
    register_ping_handlers(dp)
    register_face_swap_handlers(dp)
    # Регистрируем Stylish text ПЕРЕД image handlers, чтобы иметь приоритет
    register_stylish_text_handlers(dp)
    register_image_handlers(dp)
    register_status_handlers(dp)

