import asyncio
import sys
sys.path.insert(0, '/app')
from app.core.style_llm import test_llm_connectivity

async def main():
    print('Testing LLM connectivity...')
    results = await test_llm_connectivity()
    print('PRIMARY:', results['primary'])
    print('FALLBACK:', results['fallback'])

if __name__ == '__main__':
    asyncio.run(main())
