#!/usr/bin/env python3
file_path = '/app/app/image.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Замена 1: Добавляем Flux 2 Flex и обновляем Seedream на Seedream 4.5
old1 = '• **Nano Banana** — топовая нейросеть, пишет только заголовки на кириллице\n        "• **Seedream** — качественная нейросеть, пишет текст только на английском языке'
new1 = '• **Flux 2 Flex** — быстрая и качественная нейросеть, поддерживает кириллицу\n        "• **Nano Banana** — топовая нейросеть, пишет только заголовки на кириллице\n        "• **Seedream 4.5** — качественная нейросеть, пишет текст только на английском языке'
content = content.replace(old1, new1)

# Замена 2: Обновляем описание Flux 2 Flex
old2 = '• **Flux 2 Flex** — современная модель с улучшенной типографикой и рендерингом текста'
new2 = '• **Flux 2 Flex** — быстрая и качественная нейросеть, поддерживает кириллицу'
content = content.replace(old2, new2)

# Замена 3: Если есть просто Seedream без Flux перед ним
old3 = '"• **Seedream** — качественная нейросеть, пишет текст только на английском языке'
new3 = '"• **Seedream 4.5** — качественная нейросеть, пишет текст только на английском языке'
content = content.replace(old3, new3)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print('Updated successfully')

