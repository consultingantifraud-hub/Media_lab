#!/usr/bin/env python3
# -*- coding: utf-8 -*-

file_path = "/opt/media-lab/app/bot/handlers/start.py"

# Правильная строка БЕЗ опечаток
correct_text = "⚠️ **Важно:** Если происходит задержка ответа или возникает ошибка, нажмите кнопку «ℹ️ Info» для сброса сессии и повторите попытку заново."

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Находим и заменяем строку с "Важно:"
    for i, line in enumerate(lines):
        if 'Важно:' in line:
            # Извлекаем отступы и кавычки из оригинальной строки
            indent = len(line) - len(line.lstrip())
            # Создаем правильную строку с сохранением формата
            new_line = ' ' * indent + f'"{correct_text}\\n"\n'
            lines[i] = new_line
            print(f"Строка {i+1} заменена")
            print(f"Было: {line.rstrip()}")
            print(f"Стало: {new_line.rstrip()}")
            break
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print("✅ Файл сохранен")
    
    # Проверяем результат
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
        if 'нажмите кнопку' in content and 'нажмитее' not in content:
            print("✅ Проверка: опечатки исправлены")
        else:
            print("❌ Проверка: опечатки все еще есть")
            for line in content.split('\n'):
                if 'Важно:' in line:
                    print(f"Текущая: {line.strip()}")
            
except Exception as e:
    print(f"❌ Ошибка: {e}")
    import traceback
    traceback.print_exc()

