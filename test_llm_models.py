import sys
import os
from pathlib import Path

sys.path.insert(0, '/app')

from app.providers.fal.client import run_model

test_prompt = 'Верни JSON: {" test\: true}'

models_to_test = [
 'google/gemini-flash-1.5',
 'meta-llama/llama-3.2-3b-instruct',
 'anthropic/claude-3.5-sonnet',
]

formats_to_test = [
 {'name': 'С input', 'payload': {'input': {'model': None, 'prompt': test_prompt, 'temperature': 0.1, 'max_tokens': 100}}},
 {'name': 'Без input', 'payload': {'model': None, 'prompt': test_prompt, 'temperature': 0.1, 'max_tokens': 100}},
]

for model in models_to_test:
 print(f'\n=== Тест модели: {model} ===')
 for fmt in formats_to_test:
 payload = fmt['payload'].copy()
 if 'input' in payload:
 payload['input']['model'] = model
 else:
 payload['model'] = model
 
 print(f'\nФормат: {fmt[\name\]}')
 print(f'Payload: {payload}')
 try:
 result = run_model('fal-ai/any-llm', payload)
 print(f' УСПЕХ! Тип: {type(result)}')
 if isinstance(result, dict):
 print(f'Ключи: {list(result.keys())}')
 for key in ['output', 'text', 'content']:
 if key in result:
 val = result[key]
 if isinstance(val, str):
 print(f'Ответ в {key}: {val[:100]}')
 break
 print('---')
 break
 except Exception as e:
 print(f' Ошибка: {type(e).__name__}: {str(e)[:200]}')
