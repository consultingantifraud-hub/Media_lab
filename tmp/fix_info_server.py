#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
import sys

file_path = "/opt/media-lab/app/bot/handlers/start.py"

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Исправляем опечатки
    content = re.sub(r'нажммите', 'нажмите', content)
    content = re.sub(r'нажмитее', 'нажмите', content)
    content = re.sub(r'кноопку', 'кнопку', content)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    # Проверяем результат
    if 'нажмите кнопку' in content:
        print("✅ Текст исправлен успешно")
        # Находим строку с "Важно:"
        for line in content.split('\n'):
            if 'Важно:' in line:
                print(line.strip())
                break
    else:
        print("❌ Ошибка исправления")
        sys.exit(1)
        
except Exception as e:
    print(f"❌ Ошибка: {e}")
    sys.exit(1)

