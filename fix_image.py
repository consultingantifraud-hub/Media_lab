#!/usr/bin/env python3
# Скрипт для обновления файла image.py на сервере

file_path = '/app/app/bot/image.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Замена 1: Добавляем Flux 2 Flex и обновляем Seedream на Seedream 4.5
old_pattern1 = '• **Nano Banana** — топовая нейросеть, пишет только заголовки на кириллице\n                "• **Seedream** — качественная нейросеть, пишет текст только на английском языке'
new_pattern1 = '• **Flux 2 Flex** — быстрая и качественная нейросеть, поддерживает кириллицу\n                "• **Nano Banana** — топовая нейросеть, пишет только заголовки на кириллице\n                "• **Seedream 4.5** — качественная нейросеть, пишет текст только на английском языке'
content = content.replace(old_pattern1, new_pattern1)

# Замена 2: Обновляем описание Flux 2 Flex и Seedream на Seedream 4.5
old_pattern2 = '• **Flux 2 Flex** — современная модель с улучшенной типографикой и рендерингом текста\n        "• **Nano Banana** — топовая нейросеть, пишет только заголовки на кириллице\n        "• **Seedream** — качественная нейросеть, пишет текст только на английском языке'
new_pattern2 = '• **Flux 2 Flex** — быстрая и качественная нейросеть, поддерживает кириллицу\n        "• **Nano Banana** — топовая нейросеть, пишет только заголовки на кириллице\n        "• **Seedream 4.5** — качественная нейросеть, пишет текст только на английском языке'
content = content.replace(old_pattern2, new_pattern2)

# Замена 3: Если есть просто Seedream без Flux 2 Flex перед ним
old_pattern3 = '"• **Seedream** — качественная нейросеть, пишет текст только на английском языке'
new_pattern3 = '"• **Seedream 4.5** — качественная нейросеть, пишет текст только на английском языке'
content = content.replace(old_pattern3, new_pattern3)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print('File updated successfully')

