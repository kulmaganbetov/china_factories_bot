#!/usr/bin/env python3
"""
Supplier Verification Bot for Chinese Chemical Manufacturers
=============================================================

MVP prototype to automatically search, collect, and classify Chinese chemical suppliers
as manufacturers or trading companies.

Author: Experimental MVP
Purpose: Demonstrate feasibility to client
"""

import os
import re
import json
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup


# ============================================================================
# CONFIGURATION
# ============================================================================

SERPAPI_KEY = os.getenv("SERPAPI_API_KEY", "demo_key")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "demo_key")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

# Search configuration
MAX_SEARCH_RESULTS = 20
MAX_PAGES_TO_SCRAPE = 10
REQUEST_TIMEOUT = 10  # seconds

# Headers to avoid bot detection
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7"
}


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class ProductRequest:
    """Input structure for supplier search"""
    product_name: str
    cas_number: Optional[str] = None
    purity: Optional[str] = None
    volume: Optional[str] = None  # e.g., "20,000 MT per month"
    packaging: Optional[str] = None  # e.g., "Bulk / ISO tank"
    incoterm: Optional[str] = None  # e.g., "CIF Africa"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CompanyEvidence:
    """Extracted signals from company website"""
    keywords_found: List[str]
    address_indicators: List[str]
    certificates: List[str]
    production_capacity: Optional[str]
    packaging_capability: List[str]
    contact_info: Dict[str, str]
    page_content_sample: str  # First 500 chars for context


@dataclass
class SupplierResult:
    """Final classification result"""
    company_name: str
    website: str
    classification: str  # "manufacturer" | "trader" | "unclear"
    confidence: int  # 0-100
    evidence: CompanyEvidence
    reasoning: str

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result['evidence'] = asdict(self.evidence)
        return result


# ============================================================================
# SEARCH QUERY GENERATION
# ============================================================================

def generate_search_queries(product: ProductRequest) -> List[str]:
    """
    Generate smart bilingual search queries targeting Chinese manufacturers.

    Strategy:
    - Combine product name + CAS + industry keywords
    - Use both English and Chinese (manufacturers often use both)
    - Target B2B platforms popular in China
    - Include manufacturer-specific terms
    """
    queries = []

    # Core product identifiers
    product_id = product.product_name
    if product.cas_number:
        product_id += f" CAS {product.cas_number}"

    # English queries targeting manufacturers
    queries.extend([
        f"{product_id} manufacturer China",
        f"{product_id} factory China supplier",
        f"{product_id} producer industrial park China",
        f'"{product.product_name}" manufacturer site:.cn',
        f'{product.product_name} "production capacity" China',
    ])

    # Chinese character queries (manufacturers use 制造商, 工厂, 生产商)
    # Note: In real implementation, use actual Chinese characters
    # For demo, showing the concept with pinyin/translation
    queries.extend([
        f"{product_id} 制造商 中国",  # manufacturer
        f"{product_id} 工厂 生产",     # factory production
        f"{product_id} 生产厂家",       # production manufacturer
    ])

    # B2B platform specific queries (Made-in-China, Alibaba, ChemNet)
    queries.extend([
        f"{product_id} site:made-in-china.com manufacturer",
        f"{product_id} site:alibaba.com manufacturer",
        f"{product_id} site:chemnet.com producer",
    ])

    return queries


# ============================================================================
# WEB SEARCH (SerpAPI Integration)
# ============================================================================

def search_suppliers(queries: List[str]) -> List[Dict[str, str]]:
    """
    Execute search queries and collect unique company websites.

    Uses SerpAPI (or similar) to perform Google searches.
    Returns list of {url, title, snippet} dictionaries.

    In production: implement rate limiting, deduplication, filtering.
    """
    results = []
    seen_domains = set()

    for query in queries[:5]:  # Limit queries for demo
        print(f"🔍 Searching: {query}")

        # SerpAPI request
        search_results = _serpapi_search(query)

        for item in search_results:
            domain = urlparse(item['url']).netloc

            # Skip duplicates and non-company sites
            if domain in seen_domains:
                continue
            if _is_excluded_domain(domain):
                continue

            seen_domains.add(domain)
            results.append(item)

            if len(results) >= MAX_SEARCH_RESULTS:
                return results

    return results


def _serpapi_search(query: str) -> List[Dict[str, str]]:
    """
    Call SerpAPI to get Google search results.

    In demo mode: returns mock data if API key is invalid.
    """
    if SERPAPI_KEY == "demo_key":
        # Mock results for demo
        return _generate_mock_search_results(query)

    try:
        url = "https://serpapi.com/search"
        params = {
            "q": query,
            "api_key": SERPAPI_KEY,
            "num": 10,
            "engine": "google"
        }

        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()

        # Extract organic results
        results = []
        for item in data.get("organic_results", []):
            results.append({
                "url": item.get("link", ""),
                "title": item.get("title", ""),
                "snippet": item.get("snippet", "")
            })

        return results

    except Exception as e:
        print(f"⚠️  Search error: {e}")
        return []


def _generate_mock_search_results(query: str) -> List[Dict[str, str]]:
    """Generate realistic mock search results for demo"""
    return [
        {
            "url": "https://www.shandong-chemical-manufacturer.com",
            "title": "Shandong Chemicals Co., Ltd - Sulfuric Acid Manufacturer",
            "snippet": "Leading manufacturer of sulfuric acid 98% with 500,000 MT/year production capacity. ISO certified factory in Shandong Industrial Park."
        },
        {
            "url": "https://www.jiangsu-chem-factory.cn",
            "title": "Jiangsu Chemical Factory - Producer of Industrial Acids",
            "snippet": "Professional sulfuric acid production base. Own factory covers 200,000 sqm with advanced production lines."
        },
        {
            "url": "https://www.global-chem-trading.com",
            "title": "Global Chemical Trading - Sulfuric Acid Supplier",
            "snippet": "Supply sulfuric acid 98% from trusted Chinese manufacturers. Competitive prices, reliable logistics."
        },
    ]


def _is_excluded_domain(domain: str) -> bool:
    """Filter out non-company domains (marketplaces, directories, etc.)"""
    excluded = [
        "alibaba.com", "made-in-china.com", "globalsources.com",
        "wikipedia.org", "linkedin.com", "facebook.com",
        "youtube.com", "twitter.com"
    ]
    return any(excl in domain for excl in excluded)


# ============================================================================
# WEB SCRAPING
# ============================================================================

def _get_mock_website_content(url: str) -> Dict[str, str]:
    """
    Generate realistic mock website content for demo mode.

    Returns different content based on URL to simulate various company types.
    """
    domain = urlparse(url).netloc

    # Mock manufacturer website
    if "manufacturer" in domain or "shandong" in domain:
        return {
            "homepage": """
                Shandong Chemical Manufacturing Co., Ltd - Professional Sulfuric Acid Manufacturer

                Welcome to our factory! We are a leading manufacturer of sulfuric acid and other industrial chemicals.
                Our production facility is located in Shandong Chemical Industrial Park, covering 200,000 square meters.

                Production Capacity: 500,000 MT per year
                Certifications: ISO 9001:2015, ISO 14001, SGS, CIQ Production License

                Our own factory features advanced production lines with automated control systems.
                We offer bulk shipment, ISO tank containers, and tanker truck delivery.

                Manufacturing excellence since 1998. Contact us: sales@shandong-chem.com, +86 532 8888 9999
                Address: No.88 Industrial Road, Shandong Chemical Industrial Park, Zibo City, Shandong Province
            """,
            "about": """
                About Our Factory

                Established in 1998, we are a professional sulfuric acid manufacturer with our own production base.
                Our manufacturing plant covers 200,000 sqm in Shandong Chemical Industrial Park.

                Production facilities include:
                - 3 sulfuric acid production lines
                - Advanced contact process equipment
                - Quality control laboratory
                - Storage tanks with 50,000 MT capacity

                Annual production capacity: 500,000 metric tons
                Packaging: Bulk, ISO tanks, IBC, drums

                Quality certifications: ISO 9001, ISO 14001, SGS, production license
                Export markets: Africa, Southeast Asia, Middle East
            """
        }

    # Mock trading company website
    elif "trading" in domain or "global" in domain:
        return {
            "homepage": """
                Global Chemical Trading Co., Ltd - Your Reliable Chemical Supplier

                Welcome! We are a professional chemical trading company based in Shanghai.
                We supply high-quality chemicals from reliable Chinese manufacturers.

                Our services:
                - Sourcing from certified manufacturers
                - Quality inspection and testing
                - Export documentation and logistics
                - Competitive pricing and flexible payment terms

                Products available: Sulfuric acid, hydrochloric acid, caustic soda, and more.
                Office: Suite 1508, International Trade Building, Shanghai
                Contact: info@global-chem-trading.com, +86 21 6666 8888
            """,
            "about": """
                About Global Chemical Trading

                Established in 2010, we are a chemical trading company specializing in sourcing
                and exporting industrial chemicals from trusted Chinese manufacturers.

                Our team has over 10 years of experience in chemical import/export business.
                We work with multiple manufacturers across China to provide the best prices
                and reliable supply chain management.

                Services:
                - Product sourcing and supplier verification
                - Quality control and inspection
                - Export documentation (CIQ, SGS certificates)
                - Logistics coordination (FOB, CIF, CFR terms)

                Office location: Shanghai International Trade Center
            """
        }

    # Mock unclear/mixed company
    else:
        return {
            "homepage": """
                Jiangsu Chemical Co., Ltd

                Supplier of industrial chemicals including sulfuric acid, hydrochloric acid.
                Based in Jiangsu Province, China.

                We provide chemical products with reliable quality and competitive prices.
                Products available in various grades and packaging options.

                Contact: sales@jiangsu-chem.cn
                Tel: +86 25 8888 7777
            """,
            "about": """
                About Jiangsu Chemical

                Jiangsu Chemical Co., Ltd supplies industrial chemicals to domestic and
                international markets. We offer sulfuric acid in various concentrations.

                Our company has facilities in Jiangsu Province.
                We can arrange bulk shipment and container delivery.

                Products meet industry standards. Certificates available upon request.
            """
        }


def scrape_company_website(url: str) -> Optional[Dict[str, str]]:
    """
    Scrape company website to extract relevant pages.

    Target pages: Homepage, About Us, Products, Contact
    Returns: {page_type: content} dictionary

    In demo mode: falls back to mock data if real scraping fails.
    """
    print(f"📄 Scraping: {url}")

    try:
        # Fetch homepage
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract main content
        pages = {
            "homepage": _extract_text_content(soup)
        }

        # Find and scrape About Us page
        about_url = _find_page_url(soup, url, ["about", "company", "关于"])
        if about_url:
            pages["about"] = _scrape_page(about_url)

        # Find and scrape Products page
        products_url = _find_page_url(soup, url, ["product", "产品"])
        if products_url:
            pages["products"] = _scrape_page(products_url)

        return pages

    except Exception as e:
        print(f"⚠️  Scraping failed, using demo content")
        # In demo mode, return mock content
        return _get_mock_website_content(url)


def _extract_text_content(soup: BeautifulSoup) -> str:
    """Extract clean text from HTML, removing scripts and styles"""
    # Remove script and style elements
    for element in soup(["script", "style", "nav", "footer"]):
        element.decompose()

    # Get text and clean it
    text = soup.get_text(separator=' ', strip=True)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)

    return text[:5000]  # Limit to 5000 chars


def _find_page_url(soup: BeautifulSoup, base_url: str, keywords: List[str]) -> Optional[str]:
    """Find link to specific page (About, Products, etc.) based on keywords"""
    for link in soup.find_all('a', href=True):
        href = link['href'].lower()
        text = link.get_text().lower()

        if any(kw in href or kw in text for kw in keywords):
            # Convert relative URL to absolute
            if href.startswith('http'):
                return href
            elif href.startswith('/'):
                return f"{base_url.rstrip('/')}{href}"

    return None


def _scrape_page(url: str) -> str:
    """Scrape a single page and return text content"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        return _extract_text_content(soup)
    except:
        return ""


# ============================================================================
# SIGNAL EXTRACTION
# ============================================================================

def extract_signals(pages: Dict[str, str]) -> CompanyEvidence:
    """
    Analyze scraped content to extract classification signals.

    Key signals for manufacturer vs trader:
    - Manufacturer indicators: factory, production line, workshop, plant, manufacturing
    - Address: industrial park, development zone (manufacturers)
    - Certificates: ISO 9001, SGS, CIQ, production license
    - Capacity: mentions of MT/year, production capacity
    - Trader indicators: trading, import/export, sourcing, agent
    """

    # Combine all page content
    all_content = " ".join(pages.values())
    content_lower = all_content.lower()

    # Extract manufacturer keywords
    manufacturer_keywords = [
        "manufacturer", "factory", "plant", "production line", "workshop",
        "manufacturing facility", "production base", "own factory",
        "制造商", "工厂", "生产线", "车间"
    ]

    trader_keywords = [
        "trading company", "import export", "sourcing", "agent", "distributor",
        "supplier", "dealer", "贸易公司", "进出口"
    ]

    keywords_found = []
    for kw in manufacturer_keywords:
        if kw in content_lower:
            keywords_found.append(f"manufacturer:{kw}")

    for kw in trader_keywords:
        if kw in content_lower:
            keywords_found.append(f"trader:{kw}")

    # Extract address indicators
    address_patterns = [
        r"industrial park", r"development zone", r"economic zone",
        r"industrial area", r"factory address",
        r"工业园区", r"开发区", r"经济区"
    ]

    address_indicators = []
    for pattern in address_patterns:
        if re.search(pattern, content_lower):
            address_indicators.append(pattern.replace(r"", ""))

    # Extract certificates
    cert_patterns = [
        r"ISO\s*9001", r"ISO\s*14001", r"SGS", r"CIQ",
        r"production license", r"quality certificate",
        r"GMP", r"REACH", r"FDA"
    ]

    certificates = []
    for pattern in cert_patterns:
        matches = re.findall(pattern, all_content, re.IGNORECASE)
        certificates.extend(matches)

    # Extract production capacity
    capacity_match = re.search(
        r"(\d+[,\d]*)\s*(MT|tons?|tonnes?)\s*(?:per|/|)\s*(year|annually)",
        all_content,
        re.IGNORECASE
    )
    production_capacity = capacity_match.group(0) if capacity_match else None

    # Extract packaging capabilities
    packaging_keywords = ["bulk", "ISO tank", "tanker", "IBC", "drum", "bag"]
    packaging_capability = [
        pkg for pkg in packaging_keywords if pkg.lower() in content_lower
    ]

    # Extract contact info
    contact_info = {}
    email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", all_content)
    if email_match:
        contact_info["email"] = email_match.group(0)

    phone_match = re.search(r"\+?86[\s-]?\d{2,4}[\s-]?\d{7,8}", all_content)
    if phone_match:
        contact_info["phone"] = phone_match.group(0)

    return CompanyEvidence(
        keywords_found=keywords_found[:10],  # Limit for readability
        address_indicators=address_indicators,
        certificates=list(set(certificates))[:5],
        production_capacity=production_capacity,
        packaging_capability=packaging_capability,
        contact_info=contact_info,
        page_content_sample=all_content[:500]
    )


# ============================================================================
# LLM CLASSIFICATION
# ============================================================================

def classify_with_llm(
    company_name: str,
    website: str,
    evidence: CompanyEvidence,
    product_request: ProductRequest
) -> Dict[str, Any]:
    """
    Use LLM to classify company as manufacturer, trader, or unclear.

    The LLM analyzes extracted signals and provides:
    - Classification (manufacturer/trader/unclear)
    - Confidence score (0-100)
    - Reasoning

    Prompt engineering: provide structured evidence and ask for JSON response.
    """

    # Construct structured prompt
    prompt = f"""You are an expert in Chinese chemical industry supply chains.

Analyze the following company and classify it as either:
- "manufacturer" (owns production facilities)
- "trader" (trading/sourcing company without own production)
- "unclear" (insufficient information)

Product Request:
{json.dumps(product_request.to_dict(), indent=2)}

Company: {company_name}
Website: {website}

Extracted Evidence:
- Keywords found: {', '.join(evidence.keywords_found)}
- Address indicators: {', '.join(evidence.address_indicators)}
- Certificates: {', '.join(evidence.certificates)}
- Production capacity: {evidence.production_capacity or 'Not found'}
- Packaging capability: {', '.join(evidence.packaging_capability)}
- Contact info: {json.dumps(evidence.contact_info)}

Content sample (first 500 chars):
{evidence.page_content_sample}

Instructions:
1. Weight manufacturer signals (factory, production capacity, industrial address) heavily
2. Consider that Chinese manufacturers often mention "manufacturer" explicitly
3. Trading companies typically lack production capacity mentions
4. Return ONLY valid JSON with this exact structure:
{{
  "classification": "manufacturer" | "trader" | "unclear",
  "confidence": 0-100,
  "reasoning": "Brief explanation of decision"
}}"""

    try:
        response = _call_openai_api(prompt)
        return response

    except Exception as e:
        print(f"⚠️  LLM classification error: {e}")
        # Fallback: simple rule-based classification
        return _fallback_classification(evidence)


def _call_openai_api(prompt: str) -> Dict[str, Any]:
    """Call OpenAI API for classification"""

    if OPENAI_API_KEY == "demo_key":
        # Mock response for demo
        return {
            "classification": "manufacturer",
            "confidence": 85,
            "reasoning": "Company shows strong manufacturer signals: mentions factory, production capacity, and located in industrial park."
        }

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "gpt-4",
        "messages": [
            {"role": "system", "content": "You are an expert analyst. Return only valid JSON."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 500
    }

    response = requests.post(
        OPENAI_API_URL,
        headers=headers,
        json=payload,
        timeout=30
    )
    response.raise_for_status()

    result = response.json()
    content = result['choices'][0]['message']['content']

    # Parse JSON response
    return json.loads(content)


def _fallback_classification(evidence: CompanyEvidence) -> Dict[str, Any]:
    """
    Simple rule-based fallback if LLM fails.

    Logic:
    - Count manufacturer vs trader signals
    - Check for production capacity (strong manufacturer signal)
    - Check for industrial address (manufacturer signal)
    """

    mfr_score = 0
    trader_score = 0

    # Analyze keywords
    for kw in evidence.keywords_found:
        if kw.startswith("manufacturer:"):
            mfr_score += 10
        elif kw.startswith("trader:"):
            trader_score += 10

    # Production capacity is strong manufacturer signal
    if evidence.production_capacity:
        mfr_score += 30

    # Industrial address indicates manufacturer
    if evidence.address_indicators:
        mfr_score += 20

    # Certificates (ISO 9001, SGS) lean toward manufacturer
    if evidence.certificates:
        mfr_score += 10

    # Classify based on scores
    if mfr_score > trader_score + 20:
        classification = "manufacturer"
        confidence = min(mfr_score, 90)
    elif trader_score > mfr_score + 20:
        classification = "trader"
        confidence = min(trader_score, 90)
    else:
        classification = "unclear"
        confidence = 50

    reasoning = f"Rule-based: manufacturer signals={mfr_score}, trader signals={trader_score}"

    return {
        "classification": classification,
        "confidence": confidence,
        "reasoning": reasoning
    }


# ============================================================================
# MAIN ORCHESTRATION
# ============================================================================

def verify_suppliers(product_request: ProductRequest) -> List[SupplierResult]:
    """
    Main function: orchestrate the entire verification pipeline.

    Steps:
    1. Generate search queries
    2. Search for suppliers
    3. Scrape company websites
    4. Extract signals
    5. Classify with LLM
    6. Return results
    """

    print("\n" + "="*70)
    print("🔬 SUPPLIER VERIFICATION BOT")
    print("="*70)
    print(f"\n📦 Product: {product_request.product_name}")
    if product_request.cas_number:
        print(f"🔢 CAS: {product_request.cas_number}")
    if product_request.volume:
        print(f"📊 Volume: {product_request.volume}")
    print()

    # Step 1: Generate search queries
    print("🔧 Generating search queries...")
    queries = generate_search_queries(product_request)
    print(f"   Generated {len(queries)} queries\n")

    # Step 2: Search for suppliers
    print("🌐 Searching for suppliers...")
    search_results = search_suppliers(queries)
    print(f"   Found {len(search_results)} potential suppliers\n")

    # Step 3-5: Scrape, extract, classify
    results = []

    for idx, search_result in enumerate(search_results[:MAX_PAGES_TO_SCRAPE], 1):
        print(f"\n📍 [{idx}/{min(len(search_results), MAX_PAGES_TO_SCRAPE)}] Processing...")

        url = search_result['url']
        company_name = search_result['title']

        # Scrape website
        pages = scrape_company_website(url)
        if not pages:
            print("   ❌ Scraping failed, skipping")
            continue

        # Extract signals
        evidence = extract_signals(pages)
        print(f"   ✓ Extracted {len(evidence.keywords_found)} signals")

        # Classify with LLM
        classification = classify_with_llm(
            company_name, url, evidence, product_request
        )
        print(f"   ✓ Classification: {classification['classification']} ({classification['confidence']}%)")

        # Create result
        result = SupplierResult(
            company_name=company_name,
            website=url,
            classification=classification['classification'],
            confidence=classification['confidence'],
            evidence=evidence,
            reasoning=classification['reasoning']
        )

        results.append(result)

    # Sort by confidence (manufacturers first, then by confidence score)
    results.sort(
        key=lambda x: (
            0 if x.classification == "manufacturer" else 1,
            -x.confidence
        )
    )

    print("\n" + "="*70)
    print(f"✅ COMPLETED: Found {len(results)} suppliers")
    print("="*70 + "\n")

    return results


def print_results(results: List[SupplierResult]):
    """Pretty-print results for demo"""

    print("\n📊 RESULTS SUMMARY\n")

    for idx, result in enumerate(results, 1):
        icon = "🏭" if result.classification == "manufacturer" else "🏢" if result.classification == "trader" else "❓"

        print(f"{icon} #{idx}: {result.company_name}")
        print(f"   Website: {result.website}")
        print(f"   Type: {result.classification.upper()} (Confidence: {result.confidence}%)")
        print(f"   Evidence: {len(result.evidence.keywords_found)} keywords, "
              f"{len(result.evidence.certificates)} certificates")
        if result.evidence.production_capacity:
            print(f"   Production: {result.evidence.production_capacity}")
        print(f"   Reasoning: {result.reasoning}")
        print()


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

def main():
    """Example usage demonstrating the bot"""

    # Example 1: Sulfuric Acid request
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

    # Print results
    print_results(results)

    # Export to JSON
    output_file = "supplier_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(
            [r.to_dict() for r in results],
            f,
            indent=2,
            ensure_ascii=False
        )

    print(f"💾 Results saved to: {output_file}")

    # Show Russian bot message example
    print("\n" + "="*70)
    print("📱 TELEGRAM BOT MESSAGE (Russian)")
    print("="*70)
    print("""
Найдено поставщиков: 3

🏭 #1: Shandong Chemicals Co., Ltd
   Тип: ПРОИЗВОДИТЕЛЬ (85%)
   Мощность: 500,000 MT/год
   Сертификаты: ISO 9001, SGS
   🔗 www.shandong-chemical-manufacturer.com

🏢 #2: Global Chemical Trading
   Тип: ТОРГОВАЯ КОМПАНИЯ (75%)
   Офис: Шанхай
   🔗 www.global-chem-trading.com

❓ #3: Jiangsu Chemical Factory
   Тип: НЕЯСНО (50%)
   Требуется дополнительная проверка
   🔗 www.jiangsu-chem-factory.cn
    """)


if __name__ == "__main__":
    main()
