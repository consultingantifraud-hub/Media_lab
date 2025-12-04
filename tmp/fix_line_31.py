#!/usr/bin/env python3
# -*- coding: utf-8 -*-

file_path = "/opt/media-lab/app/bot/handlers/start.py"

# Правильная строка (строка 31) - точно из локального файла
correct_line_31 = '    "⚠️ **Важно:** Если происходит задержка ответа или возникает ошибка, нажмите кнопку «ℹ️ Info» для сброса сессии и повторите попытку заново.\\n"'

try:
    with open(file_path, 'rb') as f:
        raw_content = f.read()
    
    # Декодируем с разными кодировками, если нужно
    try:
        content = raw_content.decode('utf-8')
    except:
        content = raw_content.decode('utf-8', errors='ignore')
    
    lines = content.split('\n')
    
    # Находим строку с "Важно:" (должна быть строка 31, индекс 30)
    for i, line in enumerate(lines):
        if 'Важно:' in line:
            print(f"Найдена строка {i+1}: {repr(line)}")
            # Заменяем всю строку
            lines[i] = correct_line_31.rstrip('\n')
            print(f"Заменена на: {repr(lines[i])}")
            break
    
    # Сохраняем файл
    new_content = '\n'.join(lines)
    if not new_content.endswith('\n'):
        new_content += '\n'
    
    with open(file_path, 'wb') as f:
        f.write(new_content.encode('utf-8'))
    
    print("✅ Файл сохранен")
    
    # Проверяем результат
    with open(file_path, 'r', encoding='utf-8') as f:
        check_content = f.read()
        if 'нажмите кнопку' in check_content and 'нажмитее' not in check_content:
            print("✅ Проверка пройдена: опечатки исправлены")
        else:
            print("❌ Проверка не пройдена")
            for line in check_content.split('\n'):
                if 'Важно:' in line:
                    print(f"Текущая строка: {repr(line)}")
            
except Exception as e:
    print(f"❌ Ошибка: {e}")
    import traceback
    traceback.print_exc()

