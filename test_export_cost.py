#!/usr/bin/env python3
"""Простой тест функции get_model_cost_rub для проверки на сервере"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

# Импортируем функцию
from scripts.export_statistics_to_excel import get_model_cost_rub, MODEL_COSTS_USD

# Тестируем разные варианты
test_cases = [
    'fal-ai/flux-2-flex',
    'fal-ai/flux-2-pro/edit',
    'fal-ai/nano-banana-pro',
    None,
    '',
]

print("=" * 60)
print("Тест get_model_cost_rub:")
print("=" * 60)
for model in test_cases:
    cost = get_model_cost_rub(model)
    print(f"model={repr(model):35} cost={cost:8.2f} руб.")

print("\n" + "=" * 60)
print("MODEL_COSTS_USD (flux models):")
print("=" * 60)
for key in sorted(MODEL_COSTS_USD.keys()):
    if 'flux' in key.lower():
        print(f"{key}: {MODEL_COSTS_USD[key]} USD = {MODEL_COSTS_USD[key] * 90:.2f} руб.")

