## Кнопки и модели
- **🎨 Создать / Nano Banana Pro** → `fal-ai/gpt-image-1-mini/edit`
- **🎨 Создать / Nano Banana** → `fal-ai/nano-banana`
- **🎨 Создать / Seedream (Create)** → `fal-ai/bytedance/seedream/v4.5/text-to-image`
- **✏️ Изменить / Nano Banana Pro edit** → `fal-ai/nano-banana-pro/edit`
- **✏️ Изменить / Nano Banana edit** → `fal-ai/nano-banana/edit`
- **✏️ Изменить / Seedream edit** → `settings.fal_seedream_edit_model` (`fal-ai/bytedance/seedream/v4.5/edit`)
- **✨ Ретушь / Мягкая ретушь** → `fal-ai/retoucher`
- **✨ Ретушь / Усилить черты** → `settings.fal_seedream_edit_model` (`fal-ai/bytedance/seedream/v4.5/edit`)
- **Smart Merge / Nano Banana edit** → `fal-ai/nano-banana/edit`
- **Smart Merge / Seedream edit** → `settings.fal_seedream_edit_model`

## Цены и себестоимость
- **Создание Seedream** (генерация) — себестоимость $0.04 (≈ 3.6 ₽ по курсу 90), продажа 9 ₽
- **Редактирование Seedream** — себестоимость $0.04, продажа 9 ₽
- **Smart Merge Seedream** — себестоимость $0.04, продажа 9 ₽
- **Ретушь Seedream** — себестоимость $0.04, продажа 9 ₽
- **Создание Nano Banana Pro / Nano Banana** — см. `app/services/pricing.py` (`PRICE_NANO_BANANA_PRO`, `PRICE_OTHER_MODELS`)
- **UpScale** — `fal-ai/recraft/upscale/crisp` (0.004 USD), цена берётся из `get_all_prices()`

## Где искать в коде
- `app/core/config.py` — модели `fal_*`, особенно `fal_seedream_edit_model` / `fal_seedream_create_model`
- `app/services/pricing.py` — `PRICE_*`, `OPERATION_PRICES`, `PRICE_SEEDREAM`, а также описания и `get_all_prices()`
- `app/bot/handlers/image.py` — `RETOUCHER_MODE_PRESETS`, `MODEL_PRESETS`, `SMART_MERGE_*` и кнопки

