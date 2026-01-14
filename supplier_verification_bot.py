#!/usr/bin/env python3
"""
Chinese Chemical Supplier Verification Bot - Proof of Concept
Searches, scrapes, and classifies Chinese chemical manufacturers vs traders
"""

import os
import re
import json
import requests
from typing import List, Dict, Optional
from urllib.parse import urlparse
from bs4 import BeautifulSoup


# ============================================================================
# CONFIGURATION
# ============================================================================

SERPAPI_KEY = os.getenv("SERPAPI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not SERPAPI_KEY:
    raise ValueError("SERPAPI_API_KEY environment variable is required")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is required")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7"
}


# ============================================================================
# SEARCH
# ============================================================================

def search_suppliers(product: str, cas: str) -> List[Dict[str, str]]:
    """Search for suppliers using SerpAPI Google engine"""

    queries = [
        f"{product} CAS {cas} manufacturer China",
        f"{product} factory China supplier",
        f"{product} producer China site:.cn",
        f"硫酸 生产厂家 中国",  # Sulfuric acid manufacturer China
        f"{product} 制造商",     # manufacturer
    ]

    results = []
    seen_domains = set()

    for query in queries[:3]:  # Limit to 3 queries to reduce API cost
        print(f"🔍 Searching: {query}")

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

                # Filter out marketplaces and duplicates
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
            print(f"⚠️  Search error: {e}")
            continue

    return results


# ============================================================================
# SCRAPING
# ============================================================================

def scrape_website(url: str) -> Optional[str]:
    """Scrape company website and return combined text content"""

    print(f"📄 Scraping: {url}")

    pages_text = []

    # Scrape homepage
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

        # Try to find and scrape About page
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
        print(f"⚠️  Scraping failed: {e}")
        return None

    return " ".join(pages_text)[:8000]  # Limit total to 8000 chars


# ============================================================================
# SIGNAL EXTRACTION
# ============================================================================

def extract_signals(text: str) -> Dict:
    """Extract manufacturer vs trader signals from text"""

    if not text:
        return {}

    text_lower = text.lower()

    # Manufacturer keywords
    mfr_keywords = ["manufacturer", "factory", "plant", "production line",
                    "workshop", "manufacturing facility", "own factory",
                    "制造商", "工厂", "生产线", "车间", "生产厂家"]

    # Trader keywords
    trader_keywords = ["trading company", "import export", "sourcing",
                       "agent", "distributor", "贸易公司", "进出口"]

    signals = {
        "manufacturer_keywords": [],
        "trader_keywords": [],
        "certificates": [],
        "production_capacity": None,
        "address_indicators": [],
    }

    # Extract manufacturer keywords
    for kw in mfr_keywords:
        if kw in text_lower:
            signals["manufacturer_keywords"].append(kw)

    # Extract trader keywords
    for kw in trader_keywords:
        if kw in text_lower:
            signals["trader_keywords"].append(kw)

    # Extract certificates
    cert_patterns = [r"ISO\s*9001", r"ISO\s*14001", r"SGS", r"CIQ",
                     r"GMP", r"REACH", r"production license"]
    for pattern in cert_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            signals["certificates"].append(pattern.replace(r"\s*", " "))

    # Extract production capacity
    capacity_match = re.search(
        r"(\d+[,\d]*)\s*(MT|tons?|tonnes?)\s*(?:per|/|)\s*(year|annually)",
        text, re.IGNORECASE
    )
    if capacity_match:
        signals["production_capacity"] = capacity_match.group(0)

    # Extract address indicators
    addr_patterns = [r"industrial park", r"development zone", r"economic zone",
                     r"工业园区", r"开发区"]
    for pattern in addr_patterns:
        if re.search(pattern, text_lower):
            signals["address_indicators"].append(pattern.replace(r"", ""))

    return signals


# ============================================================================
# LLM CLASSIFICATION
# ============================================================================

def classify_with_llm(company: str, url: str, signals: Dict, content_sample: str) -> Dict:
    """Use OpenAI to classify company as manufacturer/trader/unclear"""

    prompt = f"""Analyze this Chinese chemical company and classify it.

Company: {company}
Website: {url}

Extracted Signals:
- Manufacturer keywords found: {', '.join(signals.get('manufacturer_keywords', [])[:5]) or 'None'}
- Trading keywords found: {', '.join(signals.get('trader_keywords', [])[:5]) or 'None'}
- Certificates: {', '.join(signals.get('certificates', [])) or 'None'}
- Production capacity: {signals.get('production_capacity') or 'Not mentioned'}
- Address indicators: {', '.join(signals.get('address_indicators', [])) or 'None'}

Content sample (first 500 chars):
{content_sample[:500]}

Task: Classify this company as:
- "manufacturer" if they own production facilities/factory
- "trader" if they are a trading/sourcing company without own production
- "unclear" if insufficient information

Return ONLY valid JSON with this structure:
{{
  "classification": "manufacturer" | "trader" | "unclear",
  "confidence": <0-100>,
  "reasoning": "<1-2 sentences explaining the decision>"
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

        # Parse JSON response
        classification = json.loads(content)
        return classification

    except Exception as e:
        print(f"⚠️  LLM error: {e}")
        raise


# ============================================================================
# MAIN ORCHESTRATION
# ============================================================================

def verify_supplier(url: str, title: str, product_context: Dict) -> Optional[Dict]:
    """Complete verification pipeline for one supplier"""

    # Step 1: Scrape website
    content = scrape_website(url)
    if not content:
        return None

    # Step 2: Extract signals
    signals = extract_signals(content)

    # Step 3: Classify with LLM
    classification = classify_with_llm(title, url, signals, content)

    # Step 4: Build result
    result = {
        "company": title,
        "website": url,
        "type": classification["classification"],
        "confidence": classification["confidence"],
        "reasoning": classification["reasoning"],
        "signals": {
            "manufacturer_keywords": signals.get("manufacturer_keywords", [])[:5],
            "trader_keywords": signals.get("trader_keywords", [])[:5],
            "certificates": signals.get("certificates", []),
            "production_capacity": signals.get("production_capacity"),
            "address_indicators": signals.get("address_indicators", [])
        }
    }

    return result


def main():
    """Main entry point"""

    # Hardcoded input (as per requirements)
    product_request = {
        "product": "Sulfuric Acid",
        "purity": "98%",
        "cas": "7664-93-9",
        "physical_state": "Liquid",
        "volume": "20,000 MT per month",
        "packaging": "Bulk / ISO tank / Tanker",
        "incoterm": "CIF Durban or Dar es Salaam",
        "hs_code": "2807.00",
        "hazard_class": "ADR Class 8 (Acids)"
    }

    print("="*70)
    print("🔬 CHINESE SUPPLIER VERIFICATION BOT - PROOF OF CONCEPT")
    print("="*70)
    print(f"\n📦 Product: {product_request['product']} {product_request['purity']}")
    print(f"🔢 CAS: {product_request['cas']}")
    print(f"📊 Volume: {product_request['volume']}")
    print(f"📦 Packaging: {product_request['packaging']}")
    print(f"🚢 Incoterm: {product_request['incoterm']}\n")

    # Step 1: Search
    print("🌐 Searching for suppliers...\n")
    search_results = search_suppliers(product_request["product"], product_request["cas"])

    if not search_results:
        print("❌ No suppliers found")
        return

    print(f"✅ Found {len(search_results)} potential suppliers\n")
    print("="*70 + "\n")

    # Step 2-4: Verify each supplier
    verified_suppliers = []

    for idx, result in enumerate(search_results[:5], 1):  # Limit to 5 for cost
        print(f"📍 [{idx}/{min(len(search_results), 5)}] {result['title'][:60]}...")

        try:
            verification = verify_supplier(result["url"], result["title"], product_request)

            if verification:
                verified_suppliers.append(verification)

                # Print result
                icon = "🏭" if verification["type"] == "manufacturer" else "🏢" if verification["type"] == "trader" else "❓"
                print(f"   {icon} Type: {verification['type'].upper()}")
                print(f"   📊 Confidence: {verification['confidence']}%")
                print(f"   💡 Reasoning: {verification['reasoning'][:80]}...")

                if verification["signals"]["production_capacity"]:
                    print(f"   🏗️  Capacity: {verification['signals']['production_capacity']}")

                print()

        except Exception as e:
            print(f"   ❌ Failed: {e}\n")
            continue

    # Sort: manufacturers first, then by confidence
    verified_suppliers.sort(key=lambda x: (0 if x["type"] == "manufacturer" else 1, -x["confidence"]))

    print("="*70)
    print(f"✅ VERIFICATION COMPLETE: {len(verified_suppliers)} suppliers classified")
    print("="*70 + "\n")

    # Output final JSON
    output_file = "supplier_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(verified_suppliers, f, indent=2, ensure_ascii=False)

    print(f"💾 Results saved to: {output_file}\n")

    # Print summary
    print("📊 SUMMARY:\n")
    for idx, supplier in enumerate(verified_suppliers, 1):
        icon = "🏭" if supplier["type"] == "manufacturer" else "🏢" if supplier["type"] == "trader" else "❓"
        print(f"{icon} #{idx}: {supplier['company'][:60]}")
        print(f"   Type: {supplier['type'].upper()} ({supplier['confidence']}%)")
        print(f"   Website: {supplier['website']}")
        if supplier["signals"]["production_capacity"]:
            print(f"   Capacity: {supplier['signals']['production_capacity']}")
        print()


if __name__ == "__main__":
    main()
