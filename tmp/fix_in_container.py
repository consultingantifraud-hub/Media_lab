#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re

file_path = "/app/app/bot/handlers/start.py"

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

content = re.sub(r'нажмитее', 'нажмите', content)
content = re.sub(r'кноопку', 'кнопку', content)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Исправлено")

