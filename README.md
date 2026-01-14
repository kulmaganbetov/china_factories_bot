# Supplier Verification Bot for Chinese Chemical Manufacturers

Экспериментальный MVP для автоматической проверки китайских поставщиков химических продуктов.

## 🎯 Purpose

Automatically search, collect, and classify Chinese chemical suppliers as:
- **Manufacturer** (производитель с собственным заводом)
- **Trading Company** (торговая компания без производства)
- **Unclear** (недостаточно информации)

## 🏗️ Architecture

Single-file Python prototype with clear pipeline:

1. **Search Query Generation** - Smart bilingual queries (English + Chinese)
2. **Web Search** - SerpAPI integration for Google/Bing results
3. **Web Scraping** - Extract company info from websites
4. **Signal Extraction** - Identify manufacturer vs trader indicators
5. **LLM Classification** - GPT-4 analyzes signals and classifies
6. **Structured Output** - JSON results with confidence scores

## 📋 Requirements

```bash
pip install -r requirements.txt
```

- Python 3.8+
- requests
- beautifulsoup4

## 🔑 API Keys (Environment Variables)

```bash
export SERPAPI_API_KEY="your_serpapi_key"
export OPENAI_API_KEY="your_openai_key"
export TELEGRAM_BOT_TOKEN="your_telegram_token"  # для будущей интеграции
```

## 🚀 Usage

### Basic Example

```python
from supplier_verification_bot import ProductRequest, verify_suppliers

# Create request
product = ProductRequest(
    product_name="Sulfuric Acid",
    cas_number="7664-93-9",
    purity="98%",
    volume="20,000 MT per month",
    packaging="Bulk / ISO tank",
    incoterm="CIF Africa"
)

# Run verification
results = verify_suppliers(product)

# Access results
for result in results:
    print(f"{result.company_name}: {result.classification} ({result.confidence}%)")
```

### Run Demo

```bash
python supplier_verification_bot.py
```

## 📊 Output Format

```json
{
  "company_name": "Shandong Chemicals Co., Ltd",
  "website": "https://www.example.com",
  "classification": "manufacturer",
  "confidence": 85,
  "evidence": {
    "keywords_found": ["manufacturer:factory", "manufacturer:production line"],
    "address_indicators": ["industrial park"],
    "certificates": ["ISO 9001", "SGS"],
    "production_capacity": "500,000 MT/year",
    "packaging_capability": ["bulk", "ISO tank"],
    "contact_info": {
      "email": "sales@example.com",
      "phone": "+86 532 12345678"
    }
  },
  "reasoning": "Strong manufacturer signals: factory mention, production capacity, industrial location"
}
```

## 🔍 Classification Signals

### Manufacturer Indicators (Производитель)
- ✅ Keywords: factory, plant, production line, workshop, manufacturing
- ✅ Address: industrial park, development zone
- ✅ Production capacity mentioned (e.g., "500,000 MT/year")
- ✅ Certificates: ISO 9001, SGS, production license
- ✅ Own facilities: "our factory", "production base"

### Trading Company Indicators (Торговая компания)
- 🔄 Keywords: trading company, import/export, sourcing, agent, distributor
- 🔄 Office location (not industrial)
- 🔄 No production capacity mentioned
- 🔄 Focus on "supply chain", "reliable sourcing"

## 🎨 Demo Mode

Without API keys, the bot runs in demo mode with mock data to showcase functionality:

```bash
python supplier_verification_bot.py
```

## 🔌 Telegram Integration (Future)

The bot is designed to be easily integrated with Telegram:

```python
# Псевдокод для Telegram бота

@bot.message_handler(commands=['search'])
def handle_search(message):
    # Parse user input
    product = parse_user_request(message.text)

    # Run verification
    results = verify_suppliers(product)

    # Send results in Russian
    bot.reply_to(message, format_results_russian(results))

def format_results_russian(results):
    msg = f"Найдено поставщиков: {len(results)}\n\n"

    for idx, result in enumerate(results, 1):
        icon = "🏭" if result.classification == "manufacturer" else "🏢"
        msg += f"{icon} #{idx}: {result.company_name}\n"
        msg += f"   Тип: {result.classification.upper()}\n"
        msg += f"   Уверенность: {result.confidence}%\n"
        if result.evidence.production_capacity:
            msg += f"   Мощность: {result.evidence.production_capacity}\n"
        msg += f"   🔗 {result.website}\n\n"

    return msg
```

## 🧪 Testing

```bash
# Test with different products
python -c "
from supplier_verification_bot import ProductRequest, verify_suppliers

products = [
    ProductRequest('Sulfuric Acid', cas_number='7664-93-9'),
    ProductRequest('Sodium Hydroxide', cas_number='1310-73-2'),
    ProductRequest('Methanol', cas_number='67-56-1')
]

for product in products:
    results = verify_suppliers(product)
    print(f'{product.product_name}: Found {len(results)} suppliers')
"
```

## ⚠️ Limitations (MVP)

This is a **demo prototype**, not production code:

- ❌ No rate limiting
- ❌ No retry logic
- ❌ No persistent storage
- ❌ Limited error handling
- ❌ No async/concurrent requests
- ❌ Mock data in demo mode

## 🎯 Production Roadmap

To make this production-ready:

1. **Database** - PostgreSQL for supplier data, cache, history
2. **Async** - Use `aiohttp` for concurrent scraping
3. **Rate Limiting** - Respect robots.txt, add delays
4. **Caching** - Redis for search results and classifications
5. **Error Recovery** - Retry logic, fallback strategies
6. **Monitoring** - Logging, metrics, alerts
7. **Security** - Input validation, sanitization, API key rotation
8. **Testing** - Unit tests, integration tests, fixtures
9. **Telegram Bot** - Full interactive bot with inline keyboards
10. **Admin Panel** - Review results, train classifier

## 📝 Notes

- **Language**: Bot outputs can be in Russian (for Telegram)
- **Search**: Uses bilingual queries (中文 + English)
- **LLM**: GPT-4 provides nuanced classification with reasoning
- **Fallback**: Rule-based classifier if LLM fails

## 🤝 Contributing

This is an MVP demo. For production use, consider:
- Adding more manufacturer signals (patents, export licenses)
- Integrating with Chinese business registries (工商局)
- OCR for business license images
- Social proof (customer reviews, certifications)

## 📄 License

MIT - Experimental prototype for client demo
