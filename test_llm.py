#!/usr/bin/env python3
"""Скрипт для тестирования подключения к LLM моделям"""
import asyncio
import sys
from pathlib import Path

# Добавляем путь к приложению
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.style_llm import test_llm_connectivity

async def main():
    print("=" * 60)
    print("Тестирование подключения к LLM моделям")
    print("=" * 60)
    
    results = await test_llm_connectivity()
    
    print("\nРезультаты тестирования:")
    print("-" * 60)
    
    for llm_type, result in results.items():
        print(f"\n{llm_type.upper()}:")
        print(f"  Модель: {result['model']}")
        print(f"  Успешно: {'✓' if result['success'] else '✗'}")
        if result['success']:
            print(f"  Время ответа: {result['response_time']:.2f}s")
        else:
            print(f"  Ошибка: {result['error']}")
    
    print("\n" + "=" * 60)
    
    # Проверяем, что хотя бы одна модель работает
    if results['primary']['success'] or results['fallback']['success']:
        print("✓ Хотя бы одна LLM модель доступна")
        return 0
    else:
        print("✗ Обе LLM модели недоступны!")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

