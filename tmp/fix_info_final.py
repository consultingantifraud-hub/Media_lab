#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re

file_path = "/opt/media-lab/app/bot/handlers/start.py"

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Исправляем все опечатки - используем точные замены
    original_content = content
    # Заменяем все варианты опечаток
    content = re.sub(r'нажмитее', 'нажмите', content)
    content = re.sub(r'нажммите', 'нажмите', content)
    content = re.sub(r'ннажмите', 'нажмите', content)
    content = re.sub(r'кноопку', 'кнопку', content)
    content = re.sub(r'ошибкаа', 'ошибка', content)
    
    if content != original_content:
        print("Исправлены опечатки")
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    # Проверяем результат
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
        if 'нажмите кнопку' in content and 'нажммите' not in content and 'нажмитее' not in content:
            print("✅ Текст исправлен успешно")
            for line in content.split('\n'):
                if 'Важно:' in line:
                    print(f"Проверка: {line.strip()}")
        else:
            print("❌ Ошибка: опечатки все еще присутствуют")
            
except Exception as e:
    print(f"❌ Ошибка: {e}")
    import traceback
    traceback.print_exc()

