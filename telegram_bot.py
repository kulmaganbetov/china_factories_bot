#!/usr/bin/env python3
"""
Chinese Chemical Supplier Verification Bot - Telegram Interface
Searches, scrapes, and classifies Chinese chemical suppliers for ANY product
"""

import os
import re
import json
import logging
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)


# ============================================================================
# CONFIGURATION
# ============================================================================

SERPAPI_KEY = os.getenv("SERPAPI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not SERPAPI_KEY:
    raise ValueError("SERPAPI_API_KEY environment variable is required")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is required")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7"
}

# Conversation states
PRODUCT_NAME, CAS_NUMBER, VOLUME, PACKAGING = range(4)

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ============================================================================
# VERIFICATION ENGINE (Universal - works for ANY product)
# ============================================================================

def search_suppliers(product: str, cas: Optional[str] = None) -> List[Dict[str, str]]:
    """Search for suppliers using SerpAPI - works for ANY chemical product"""

    # Build universal queries
    queries = [
        f"{product} manufacturer China",
        f"{product} factory China supplier",
    ]

    if cas:
        queries.insert(0, f"{product} CAS {cas} manufacturer China")
        queries.append(f"CAS {cas} producer China")

    results = []
    seen_domains = set()

    for query in queries[:3]:
        logger.info(f"Searching: {query}")

        try:
            response = requests.get("https://serpapi.com/search", params={
                "q": query,
                "api_key": SERPAPI_KEY,
                "num": 10,
                "engine": "google"
            }, timeout=15)
            response.raise_for_status()
            data = response.json()

            for item in data.get("organic_results", []):
                url = item.get("link", "")
                domain = urlparse(url).netloc

                # Filter marketplaces and duplicates
                excluded = ["alibaba.com", "made-in-china.com", "indiamart.com",
                           "globalsources.com", "wikipedia.org", "linkedin.com"]
                if any(exc in domain for exc in excluded):
                    continue
                if domain in seen_domains:
                    continue
                if url.endswith('.pdf'):
                    continue

                seen_domains.add(domain)
                results.append({
                    "url": url,
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", "")
                })

                if len(results) >= 10:
                    return results

        except Exception as e:
            logger.error(f"Search error: {e}")
            continue

    return results


def scrape_website(url: str) -> Optional[str]:
    """Scrape company website and return text content"""

    pages_text = []

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Remove scripts, styles, nav, footer
        for element in soup(["script", "style", "nav", "footer", "header"]):
            element.decompose()

        text = soup.get_text(separator=' ', strip=True)
        text = re.sub(r'\s+', ' ', text)
        pages_text.append(text[:5000])

        # Try to find About page
        about_links = soup.find_all('a', href=True)
        for link in about_links[:50]:
            href = link['href'].lower()
            link_text = link.get_text().lower()

            if any(kw in href or kw in link_text for kw in ['about', 'company', '关于', 'profile']):
                about_url = href if href.startswith('http') else url.rstrip('/') + '/' + href.lstrip('/')

                try:
                    resp = requests.get(about_url, headers=HEADERS, timeout=10)
                    resp.raise_for_status()
                    soup2 = BeautifulSoup(resp.text, 'html.parser')
                    for el in soup2(["script", "style", "nav", "footer", "header"]):
                        el.decompose()
                    about_text = soup2.get_text(separator=' ', strip=True)
                    about_text = re.sub(r'\s+', ' ', about_text)
                    pages_text.append(about_text[:3000])
                    break
                except:
                    pass

    except Exception as e:
        logger.error(f"Scraping failed for {url}: {e}")
        return None

    return " ".join(pages_text)[:8000]


def extract_signals(text: str) -> Dict:
    """Extract manufacturer vs trader signals"""

    if not text:
        return {}

    text_lower = text.lower()

    mfr_keywords = ["manufacturer", "factory", "plant", "production line",
                    "workshop", "manufacturing facility", "own factory",
                    "制造商", "工厂", "生产线", "车间", "生产厂家"]

    trader_keywords = ["trading company", "import export", "sourcing",
                       "agent", "distributor", "贸易公司", "进出口"]

    signals = {
        "manufacturer_keywords": [],
        "trader_keywords": [],
        "certificates": [],
        "production_capacity": None,
        "address_indicators": [],
    }

    for kw in mfr_keywords:
        if kw in text_lower:
            signals["manufacturer_keywords"].append(kw)

    for kw in trader_keywords:
        if kw in text_lower:
            signals["trader_keywords"].append(kw)

    cert_patterns = [r"ISO\s*9001", r"ISO\s*14001", r"SGS", r"CIQ",
                     r"GMP", r"REACH", r"production license"]
    for pattern in cert_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            signals["certificates"].append(pattern.replace(r"\s*", " "))

    capacity_match = re.search(
        r"(\d+[,\d]*)\s*(MT|tons?|tonnes?)\s*(?:per|/|)\s*(year|annually)",
        text, re.IGNORECASE
    )
    if capacity_match:
        signals["production_capacity"] = capacity_match.group(0)

    addr_patterns = [r"industrial park", r"development zone", r"economic zone",
                     r"工业园区", r"开发区"]
    for pattern in addr_patterns:
        if re.search(pattern, text_lower):
            signals["address_indicators"].append(pattern.replace(r"", ""))

    return signals


def classify_with_llm(company: str, url: str, signals: Dict, content_sample: str) -> Dict:
    """Use OpenAI to classify company"""

    prompt = f"""Analyze this Chinese chemical company and classify it.

Company: {company}
Website: {url}

Extracted Signals:
- Manufacturer keywords: {', '.join(signals.get('manufacturer_keywords', [])[:5]) or 'None'}
- Trading keywords: {', '.join(signals.get('trader_keywords', [])[:5]) or 'None'}
- Certificates: {', '.join(signals.get('certificates', [])) or 'None'}
- Production capacity: {signals.get('production_capacity') or 'Not mentioned'}
- Address indicators: {', '.join(signals.get('address_indicators', [])) or 'None'}

Content sample:
{content_sample[:500]}

Classify as:
- "manufacturer" if they own production facilities
- "trader" if trading/sourcing company without own production
- "unclear" if insufficient information

Return ONLY valid JSON:
{{
  "classification": "manufacturer" | "trader" | "unclear",
  "confidence": <0-100>,
  "reasoning": "<1-2 sentences>"
}}"""

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4",
                "messages": [
                    {"role": "system", "content": "You are an expert in Chinese chemical industry. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 300
            },
            timeout=30
        )
        response.raise_for_status()

        result = response.json()
        content = result['choices'][0]['message']['content']
        classification = json.loads(content)
        return classification

    except Exception as e:
        logger.error(f"LLM error: {e}")
        raise


def verify_supplier(url: str, title: str) -> Optional[Dict]:
    """Complete verification pipeline for one supplier"""

    content = scrape_website(url)
    if not content:
        return None

    signals = extract_signals(content)
    classification = classify_with_llm(title, url, signals, content)

    return {
        "company": title,
        "website": url,
        "type": classification["classification"],
        "confidence": classification["confidence"],
        "reasoning": classification["reasoning"],
        "signals": signals
    }


def run_verification(product: str, cas: Optional[str] = None) -> List[Dict]:
    """Main verification function - works for ANY product"""

    logger.info(f"Starting verification for: {product} (CAS: {cas or 'N/A'})")

    # Search
    search_results = search_suppliers(product, cas)
    if not search_results:
        return []

    # Verify each supplier
    verified = []
    for result in search_results[:5]:  # Limit to 5 for cost control
        try:
            verification = verify_supplier(result["url"], result["title"])
            if verification:
                verified.append(verification)
        except Exception as e:
            logger.error(f"Verification failed for {result['url']}: {e}")
            continue

    # Sort: manufacturers first, then by confidence
    verified.sort(key=lambda x: (0 if x["type"] == "manufacturer" else 1, -x["confidence"]))

    return verified


# ============================================================================
# TELEGRAM BOT INTERFACE (Russian)
# ============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command - Russian interface"""

    welcome_msg = """
🔬 <b>Бот для поиска китайских поставщиков химического сырья</b>

Этот бот поможет вам найти производителей и торговые компании в Китае.

<b>Как использовать:</b>
1. Отправьте /search чтобы начать поиск
2. Введите данные о продукте
3. Получите список проверенных поставщиков

<b>Бот классифицирует компании как:</b>
🏭 Производитель (own factory)
🏢 Торговая компания (trading)
❓ Неясно (unclear)

Используйте /search для начала поиска.
"""

    await update.message.reply_text(welcome_msg, parse_mode='HTML')


async def search_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start search conversation"""

    msg = """
📝 <b>Новый поиск поставщика</b>

Введите название химического продукта на английском языке.

<b>Примеры:</b>
- Sulfuric Acid
- Sodium Hydroxide
- Methanol
- Hydrogen Peroxide

Введите название продукта:
"""

    await update.message.reply_text(msg, parse_mode='HTML')
    return PRODUCT_NAME


async def receive_product_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive product name"""

    product_name = update.message.text.strip()
    context.user_data['product'] = product_name

    msg = f"""
✅ Продукт: <b>{product_name}</b>

Введите CAS номер (или отправьте /skip если не знаете):

<b>Пример:</b> 7664-93-9
"""

    await update.message.reply_text(msg, parse_mode='HTML')
    return CAS_NUMBER


async def receive_cas_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive CAS number"""

    cas = update.message.text.strip()
    if cas.lower() != '/skip':
        context.user_data['cas'] = cas
    else:
        context.user_data['cas'] = None

    msg = """
Введите требуемый объём (или отправьте /skip):

<b>Примеры:</b>
- 20,000 MT per month
- 500 tons per year
- 100 MT
"""

    await update.message.reply_text(msg, parse_mode='HTML')
    return VOLUME


async def receive_volume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive volume"""

    volume = update.message.text.strip()
    if volume.lower() != '/skip':
        context.user_data['volume'] = volume
    else:
        context.user_data['volume'] = None

    msg = """
Введите требования к упаковке (или отправьте /skip):

<b>Примеры:</b>
- Bulk / ISO tank
- Drums
- IBC containers
"""

    await update.message.reply_text(msg, parse_mode='HTML')
    return PACKAGING


async def receive_packaging(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive packaging and start verification"""

    packaging = update.message.text.strip()
    if packaging.lower() != '/skip':
        context.user_data['packaging'] = packaging
    else:
        context.user_data['packaging'] = None

    # Show summary and start search
    product = context.user_data['product']
    cas = context.user_data.get('cas')
    volume = context.user_data.get('volume')
    packaging = context.user_data.get('packaging')

    summary = f"""
📋 <b>Параметры поиска:</b>

🧪 Продукт: {product}
🔢 CAS: {cas or 'не указан'}
📊 Объём: {volume or 'не указан'}
📦 Упаковка: {packaging or 'не указана'}

⏳ <b>Начинаю поиск поставщиков...</b>
Это займёт 1-2 минуты.
"""

    await update.message.reply_text(summary, parse_mode='HTML')

    # Run verification
    try:
        verified_suppliers = run_verification(product, cas)

        if not verified_suppliers:
            await update.message.reply_text(
                "❌ Поставщики не найдены. Попробуйте изменить название продукта или использовать английское название."
            )
            return ConversationHandler.END

        # Format and send results
        result_msg = format_results(verified_suppliers, product)
        await update.message.reply_text(result_msg, parse_mode='HTML', disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"Verification error: {e}")
        await update.message.reply_text(
            f"❌ Ошибка при поиске: {str(e)}\n\nПопробуйте снова с помощью /search"
        )

    return ConversationHandler.END


def format_results(suppliers: List[Dict], product: str) -> str:
    """Format verification results in Russian"""

    if not suppliers:
        return "❌ Поставщики не найдены."

    msg = f"✅ <b>Найдено поставщиков: {len(suppliers)}</b>\n\n"

    for idx, supplier in enumerate(suppliers, 1):
        # Choose icon based on type
        if supplier['type'] == 'manufacturer':
            icon = "🏭"
            type_ru = "ПРОИЗВОДИТЕЛЬ"
        elif supplier['type'] == 'trader':
            icon = "🏢"
            type_ru = "ТОРГОВАЯ КОМПАНИЯ"
        else:
            icon = "❓"
            type_ru = "НЕЯСНО"

        msg += f"{icon} <b>#{idx}: {supplier['company'][:60]}</b>\n"
        msg += f"   Тип: {type_ru}\n"
        msg += f"   Уверенность: {supplier['confidence']}%\n"

        # Add production capacity if available
        if supplier['signals'].get('production_capacity'):
            msg += f"   🏗️ Мощность: {supplier['signals']['production_capacity']}\n"

        # Add certificates if available
        certs = supplier['signals'].get('certificates', [])
        if certs:
            msg += f"   📜 Сертификаты: {', '.join(certs[:3])}\n"

        msg += f"   🔗 <a href='{supplier['website']}'>{urlparse(supplier['website']).netloc}</a>\n"
        msg += f"   💡 {supplier['reasoning'][:100]}\n\n"

    msg += "\n💡 <i>Используйте /search для нового поиска</i>"

    return msg


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel conversation"""

    await update.message.reply_text(
        "❌ Поиск отменён. Используйте /search для нового поиска."
    )
    return ConversationHandler.END


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Run Telegram bot"""

    # Create application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Conversation handler for search
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('search', search_start)],
        states={
            PRODUCT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_product_name)],
            CAS_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_cas_number)],
            VOLUME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_volume)],
            PACKAGING: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_packaging)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    # Add handlers
    application.add_handler(CommandHandler('start', start))
    application.add_handler(conv_handler)

    # Start bot
    logger.info("🤖 Telegram bot started")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
