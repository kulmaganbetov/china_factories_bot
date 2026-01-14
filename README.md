# Chinese Chemical Supplier Verification Bot

**Proof-of-Concept** для автоматической верификации китайских поставщиков химического сырья.

## 🎯 Цель

Автоматически искать китайских поставщиков и классифицировать их как:
- **Manufacturer** (производитель с собственным заводом)
- **Trader** (торговая компания без производства)
- **Unclear** (недостаточно информации)

## 🏗️ Как работает

1. **Поиск** → Ищет компании через SerpAPI (Google)
2. **Скрейпинг** → Извлекает текст с сайтов компаний
3. **Извлечение сигналов** → Находит ключевые слова, сертификаты, мощности
4. **Классификация LLM** → OpenAI GPT-4 анализирует данные и классифицирует
5. **Результат** → JSON с типом компании, уверенностью и обоснованием

## 📋 Требования

```bash
pip install requests beautifulsoup4
```

Python 3.8+

## 🔑 API Ключи (ОБЯЗАТЕЛЬНО)

Без ключей код **не работает**. Это proof-of-concept, не демо.

```bash
export SERPAPI_API_KEY="ваш_ключ_serpapi"
export OPENAI_API_KEY="ваш_ключ_openai"
```

Получить ключи:
- SerpAPI: https://serpapi.com/
- OpenAI: https://platform.openai.com/api-keys

## 🚀 Запуск

```bash
python supplier_verification_bot.py
```

Пример хардкоднут в коде:
- Продукт: Sulfuric Acid 98%
- CAS: 7664-93-9
- Объем: 20,000 MT/месяц
- Упаковка: Bulk / ISO tank
- Условия: CIF Durban / Dar es Salaam

## 📊 Что извлекается

### Сигналы производителя
- Ключевые слова: factory, plant, production line, workshop, 工厂, 制造商
- Адрес: industrial park, development zone, 工业园区
- Мощность производства: "500,000 MT/year"
- Сертификаты: ISO 9001, SGS, CIQ, production license

### Сигналы торговой компании
- Ключевые слова: trading company, sourcing, agent, distributor, 贸易公司
- Офисный адрес (не промзона)
- Нет упоминания производственных мощностей

## 📄 Формат результата

```json
{
  "company": "Shandong Chemical Manufacturing Co., Ltd",
  "website": "https://example.com",
  "type": "manufacturer",
  "confidence": 85,
  "reasoning": "Company has own factory with 500,000 MT/year capacity in industrial park",
  "signals": {
    "manufacturer_keywords": ["factory", "plant", "production line"],
    "trader_keywords": [],
    "certificates": ["ISO 9001", "SGS"],
    "production_capacity": "500,000 MT per year",
    "address_indicators": ["industrial park"]
  }
}
```

## ⚙️ Архитектура

**Файл:** `supplier_verification_bot.py` (308 строк)

**Основные функции:**
- `search_suppliers()` → SerpAPI поиск
- `scrape_website()` → Извлечение текста с сайта
- `extract_signals()` → Поиск сигналов (keywords, capacity, certificates)
- `classify_with_llm()` → OpenAI классификация
- `verify_supplier()` → Полный пайплайн для одной компании
- `main()` → Оркестрация

## 🔌 Интеграция с Telegram

Код готов к интеграции. Пример:

```python
from supplier_verification_bot import search_suppliers, verify_supplier

@bot.message_handler(commands=['search'])
def handle_search(message):
    # Парсим запрос пользователя
    product = "Sulfuric Acid"
    cas = "7664-93-9"

    # Ищем
    results = search_suppliers(product, cas)

    # Верифицируем
    verified = []
    for result in results[:5]:
        supplier = verify_supplier(result["url"], result["title"], {})
        if supplier:
            verified.append(supplier)

    # Отправляем результат на русском
    msg = format_russian(verified)
    bot.reply_to(message, msg)

def format_russian(suppliers):
    msg = f"Найдено поставщиков: {len(suppliers)}\n\n"
    for idx, s in enumerate(suppliers, 1):
        icon = "🏭" if s["type"] == "manufacturer" else "🏢"
        msg += f"{icon} #{idx}: {s['company']}\n"
        msg += f"   Тип: {s['type'].upper()}\n"
        msg += f"   Уверенность: {s['confidence']}%\n"
        if s["signals"]["production_capacity"]:
            msg += f"   Мощность: {s['signals']['production_capacity']}\n"
        msg += f"   🔗 {s['website']}\n\n"
    return msg
```

## 🧪 Тестирование

Без API ключей:
```bash
$ python supplier_verification_bot.py
ValueError: SERPAPI_API_KEY environment variable is required
```

С API ключами:
```bash
$ export SERPAPI_API_KEY="..."
$ export OPENAI_API_KEY="..."
$ python supplier_verification_bot.py

🔍 Searching: Sulfuric Acid CAS 7664-93-9 manufacturer China
📄 Scraping: https://example-manufacturer.com
🏭 Type: MANUFACTURER
📊 Confidence: 90%
💡 Reasoning: Has own factory with 500k MT/year capacity in Shandong Industrial Park
```

## 🎯 Особенности proof-of-concept

✅ Реальный поиск через SerpAPI
✅ Реальный скрейпинг сайтов
✅ Реальная классификация через OpenAI
✅ Билингвальные запросы (中文 + English)
✅ Извлечение структурированных сигналов
✅ JSON выход с обоснованием
✅ Готов к интеграции с Telegram

❌ Нет БД (in-memory)
❌ Нет async (синхронный)
❌ Нет retry логики
❌ Нет кэширования
❌ Нет rate limiting

## 📝 Для production

Нужно добавить:
1. PostgreSQL для хранения результатов
2. Redis для кэширования
3. Async/await для параллельного скрейпинга
4. Retry логику с exponential backoff
5. Rate limiting для API
6. Логирование и мониторинг
7. Telegram бот с inline keyboard
8. Admin панель для проверки результатов

## 📊 Стоимость

Примерная стоимость на 1 поиск:
- SerpAPI: $0.003 × 3 запроса = $0.009
- OpenAI GPT-4: $0.03 × 5 компаний = $0.15
- **Итого: ~$0.16 на поиск**

Для снижения стоимости:
- Использовать GPT-3.5-turbo вместо GPT-4 (-80%)
- Кэшировать результаты (Redis)
- Ограничить до 3 компаний вместо 5

## 🔒 Безопасность

- API ключи через environment variables
- Не коммитим `.env` файл
- User-Agent для скрейпинга
- Timeout на requests
- Фильтрация URL (no PDFs, marketplaces)

## 📄 Файлы

- `supplier_verification_bot.py` - Основной код (308 строк)
- `requirements.txt` - Зависимости
- `.env.example` - Пример конфига
- `.gitignore` - Исключения
- `README.md` - Документация

## 🤝 Пример использования

```python
from supplier_verification_bot import verify_supplier

result = verify_supplier(
    url="https://shandong-chemical.com",
    title="Shandong Chemical Co., Ltd",
    product_context={"product": "Sulfuric Acid", "cas": "7664-93-9"}
)

print(f"Type: {result['type']}")
print(f"Confidence: {result['confidence']}%")
print(f"Reasoning: {result['reasoning']}")
```

## 📞 Telegram Bot Message (Пример)

```
Найдено поставщиков: 3

🏭 #1: Shandong Chemical Manufacturing Co., Ltd
   Тип: ПРОИЗВОДИТЕЛЬ (90%)
   Мощность: 500,000 MT/год
   Сертификаты: ISO 9001, SGS, CIQ
   🔗 www.shandong-chemical.com

🏢 #2: Shanghai Global Trading Co., Ltd
   Тип: ТОРГОВАЯ КОМПАНИЯ (85%)
   Офис: Шанхай, International Trade Center
   🔗 www.shanghai-trading.com

❓ #3: Jiangsu Chemical Co., Ltd
   Тип: НЕЯСНО (60%)
   Требуется дополнительная проверка
   🔗 www.jiangsu-chem.cn
```

## ⚠️ Disclaimer

Это **proof-of-concept** код для демонстрации возможности автоматической верификации поставщиков. Не использовать в production без доработки (БД, error handling, rate limiting, monitoring).

## 📜 License

MIT
