#!/usr/bin/env python3
# -*- coding: utf-8 -*-

file_path = "/opt/media-lab/app/bot/handlers/start.py"

# Правильная строка из локального файла
correct_line = '    "⚠️ **Важно:** Если происходит задержка ответа или возникает ошибка, нажмите кнопку «ℹ️ Info» для сброса сессии и повторите попытку заново.\\n"\n'

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Находим и заменяем строку с "Важно:"
    found = False
    for i, line in enumerate(lines):
        if 'Важно:' in line:
            print(f"Найдена строка {i+1}")
            print(f"Было: {line.rstrip()}")
            lines[i] = correct_line
            print(f"Стало: {correct_line.rstrip()}")
            found = True
            break
    
    if not found:
        print("❌ Строка с 'Важно:' не найдена")
    else:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        
        # Проверяем результат
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            if 'нажмите кнопку' in content and 'нажммите' not in content and 'нажмитее' not in content and 'ннажмите' not in content:
                print("✅ Текст исправлен успешно")
                for line in content.split('\n'):
                    if 'Важно:' in line:
                        print(f"Проверка: {line.strip()}")
            else:
                print("❌ Ошибка: опечатки все еще присутствуют")
                for line in content.split('\n'):
                    if 'Важно:' in line:
                        print(f"Текущая строка: {line.strip()}")
            
except Exception as e:
    print(f"❌ Ошибка: {e}")
    import traceback
    traceback.print_exc()

