#!/usr/bin/env python3
file_path = '/app/app/bot/image.py'
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Исправляем строку с неправильным Flux 2 Flex
for i in range(len(lines)):
    if 'Flux 2 Flex** быстрая' in lines[i] or ('Flux 2 Flex' in lines[i] and '•' not in lines[i]):
        lines[i] = '                "• **Flux 2 Flex** — быстрая и качественная нейросеть, поддерживает кириллицу\\n"\n'
        print(f'Fixed line {i+1}')
        break

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('Done')

