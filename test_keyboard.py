#!/usr/bin/env python3
import sys
sys.path.insert(0, '/app')
from app.bot.keyboards.main import build_create_model_keyboard, IMAGE_SEEDREAM_CREATE_BUTTON, IMAGE_FLUX2FLEX_CREATE_BUTTON

print("=== КОНСТАНТЫ ===")
print(f"IMAGE_SEEDREAM_CREATE_BUTTON = {repr(IMAGE_SEEDREAM_CREATE_BUTTON)}")
print(f"IMAGE_FLUX2FLEX_CREATE_BUTTON = {repr(IMAGE_FLUX2FLEX_CREATE_BUTTON)}")

print("\n=== КЛАВИАТУРА ===")
kb = build_create_model_keyboard()
for i, row in enumerate(kb.keyboard):
    btn_texts = [btn.text for btn in row]
    print(f"Row {i}: {btn_texts}")

print("\n=== ПРОВЕРКА ===")
all_buttons = [btn.text for row in kb.keyboard for btn in row]
if "Seedream 4.5" in all_buttons:
    print("✓ Кнопка 'Seedream 4.5' найдена")
else:
    print("✗ Кнопка 'Seedream 4.5' НЕ найдена!")
    print(f"  Найдены кнопки: {all_buttons}")

if "Flux 2 Flex" in all_buttons:
    print("✓ Кнопка 'Flux 2 Flex' найдена")
else:
    print("✗ Кнопка 'Flux 2 Flex' НЕ найдена!")

