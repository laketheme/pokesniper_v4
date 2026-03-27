import asyncio
import aiohttp
import re
import json
import logging
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from config import AU_RETAILERS, MAX_CONCURRENT, MODERN_SETS
from checker import get_headers

logger = logging.getLogger("pokemon_sniper")
ua = UserAgent()
semaphore = asyncio.Semaphore(MAX_CONCURRENT)

# Patterns to identify Pokemon TCG products in URLs/titles
POKEMON_PRODUCT_PATTERNS = [
    re.compile(r"pokemon", re.IGNORECASE),
    re.compile(r"pok[eé]mon", re.IGNORECASE),
]

# Filter out non-TCG products (plush, figures, games, etc.)
EXCLUDE_PATTERNS = [
    re.compile(r"plush|plushie|soft\s*toy", re.IGNORECASE),
    re.compile(r"figure|figurine|statue", re.IGNORECASE),
    re.compile(r"video\s*game|nintendo|switch|scarlet|violet|legends|arceus", re.IGNORECASE),
    re.compile(r"t-?shirt|hoodie|apparel|clothing|hat|cap", re.IGNORECASE),
    re.compile(r"poster(?!\s*collection)|wall\s*art|print(?!\s)", re.IGNORECASE),
    re.compile(r"mug|cup|keychain|lanyard|badge|pin(?!k)", re.IGNORECASE),
    re.compile(r"backpack|bag|wallet|case(?!\s)", re.IGNORECASE),
    re.compile(r"blanket|towel|cushion|pillow", re.IGNORECASE),
    re.compile(r"board\s*game|puzzle|lego|mega\s*construx", re.IGNORECASE),
    re.compile(r"sleeve|deck\s*box|binder(?!\s*collection)|play\s*mat|dice|coin", re.IGNORECASE),
]

# TCG product keywords (must match at least one)
TCG_KEYWORDS = [
    re.compile(r"booster|etb|elite\s*trainer|trainer\s*box", re.IGNORECASE),
    re.compile(r"collection\s*box|premium\s*collection", re.IGNORECASE),
    re.compile(r"booster\s*box|booster\s*bundle", re.IGNORECASE),
    re.compile(r"blister|3[\s-]*pack|single\s*pack", re.IGNORECASE),
    re.compile(r"tin\b|ultra\s*premium", re.IGNORECASE),
    re.compile(r"build\s*(?:&|and)\s*battle", re.IGNORECASE),
    re.compile(r"tcg|trading\s*card", re.IGNORECASE),
    re.compile(r"special\s*illustration", re.IGNORECASE),
    re.compile(r"binder\s*collection|poster\s*collection", re.IGNORECASE),
    re.compile(r"tech\s*sticker|super\s*premium", re.IGNORECASE),
]


def is_modern_set(text: str) -> bool:
    """Check if a product name references a modern (current) set."""
    text_lower = text.lower()
    for s in MODERN_SETS:
        if s.lower() in text_lower:
            return True
    # If no set name detected, still include — could be a generic listing
    return True


def is_pokemon_tcg_product(name: str, url: str = "") -> bool:
    """Determine if a product is a Pokemon TCG product (not merch/games)."""
    combined = f"{name} {url}"
    
    # Must mention Pokemon
    if not any(p.search(combined) for p in POKEMON_PRODUCT_PATTERNS):
        return False
    
    # Must NOT be merch
    if any(p.search(name) for p in EXCLUDE_PATTERNS):
        return False
    
    # Must match at least one TCG keyword
    if any(p.search(combined) for p in TCG_KEYWORDS):
        return True
    
    return False


async def discover_shopify(session: aiohttp.ClientSession, retailer_key: str, 
                           retailer_info: dict) -> list:
    """Discover products from Shopify-based AU retailers."""
    found = []
    base = retailer_info["base_url"]
    
    # Try multiple collection endpoints
    endpoints = [
        f"{base}/collections/trading-card-game/products.json?limit=250",
        f"{base}/collections/pokemon/products.json?limit=250",
        f"{base}/collections/pokemon-tcg/products.json?limit=250",
        f"{base}/collections/pokemon-trading-card-game/products.json?limit=250",
        f"{base}/collections/all/products.json?limit=250",
        f"{base}/products.json?limit=250",
    ]
    
    seen_urls = set()
    
    for endpoint in endpoints:
        try:
            async with semaphore:
                async with session.get(endpoint, headers=get_headers(), 
                                       timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
                    products = data.get("products", [])
                    
                    for p in products:
                        title = p.get("title", "")
                        handle = p.get("handle", "")
                        product_url = f"{base}/products/{handle}"
                        
                        if product_url in seen_urls:
                            continue
                        
                        if is_pokemon_tcg_product(title, product_url) and is_modern_set(title):
                            variants = p.get("variants", [])
                            price = min((float(v.get("price", "999")) for v in variants), default=0)
                            available = any(v.get("available", False) for v in variants)
                            
                            seen_urls.add(product_url)
                            found.append({
                                "url": product_url,
                                "name": title,
                                "retailer": retailer_key,
                                "price": price,
                                "available": available,
                                "source": "shopify_api",
                            })
        except Exception as e:
            logger.debug(f"Shopify discovery failed for {endpoint}: {e}")
            continue
    
    return found


async def discover_html(session: aiohttp.ClientSession, retailer_key: str,
                        retailer_info: dict) -> list:
    """Discover products from HTML-based AU retailers via search/category pages."""
    found = []
    search_url = retailer_info.get("search_url", "")
    base = retailer_info["base_url"]
    
    if not search_url:
        return found
    
    # Also try Pokemon TCG specific searches
    search_urls = [search_url]
    
    # Add modern set searches
    for set_name in MODERN_SETS[:5]:  # Top 5 most recent sets
        encoded = set_name.replace(" ", "+").replace("&", "%26")
        if "search" in search_url:
            if "q=" in search_url:
                search_urls.append(re.sub(r'q=[^&]*', f'q=pokemon+{encoded}', search_url))
            elif "text=" in search_url:
                search_urls.append(re.sub(r'text=[^&]*', f'text=pokemon+{encoded}', search_url))
    
    seen_urls = set()
    
    for url in search_urls:
        try:
            async with semaphore:
                async with session.get(url, headers=get_headers(),
                                       timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status != 200:
                        continue
                    html = await resp.text()
        except Exception as e:
            logger.debug(f"HTML discovery failed for {url}: {e}")
            continue
        
        soup = BeautifulSoup(html, "html.parser")
        
        # Find product links — common patterns across retailers
        link_patterns = [
            soup.find_all("a", href=re.compile(r"/product[s]?/", re.IGNORECASE)),
            soup.find_all("a", href=re.compile(r"/p/", re.IGNORECASE)),
            soup.find_all("a", class_=re.compile(r"product", re.IGNORECASE)),
            soup.find_all("a", {"data-product": True}),
        ]
        
        for links in link_patterns:
            for link in links:
                href = link.get("href", "")
                if not href:
                    continue
                
                # Make absolute URL
                if href.startswith("/"):
                    href = base + href
                elif not href.startswith("http"):
                    continue
                
                # Only links from this retailer
                if base.replace("https://", "").replace("www.", "") not in href:
                    continue
                
                if href in seen_urls:
                    continue
                
                # Get product name from link text, title attr, or child elements
                name = (link.get("title", "") or link.get_text(strip=True) or 
                        link.get("aria-label", ""))
                
                if not name or len(name) < 5:
                    # Try to find name in parent card
                    parent = link.find_parent(class_=re.compile(r"product|card|item", re.IGNORECASE))
                    if parent:
                        heading = parent.find(re.compile(r"h[2-4]|span|p", re.IGNORECASE),
                                              class_=re.compile(r"title|name|heading", re.IGNORECASE))
                        if heading:
                            name = heading.get_text(strip=True)
                
                if name and is_pokemon_tcg_product(name, href) and is_modern_set(name):
                    seen_urls.add(href)
                    found.append({
                        "url": href,
                        "name": name[:200],
                        "retailer": retailer_key,
                        "price": 0,
                        "available": None,
                        "source": "html_scrape",
                    })
    
    return found


async def discover_all_products(target_retailers: list = None) -> list:
    """Scan all (or specified) AU retailers for Pokemon TCG products."""
    all_found = []
    
    retailers = {k: v for k, v in AU_RETAILERS.items() 
                 if target_retailers is None or k in target_retailers}
    
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = []
        for key, info in retailers.items():
            if info.get("type") == "shopify":
                tasks.append(discover_shopify(session, key, info))
            else:
                tasks.append(discover_html(session, key, info))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for r in results:
        if isinstance(r, Exception):
            logger.error(f"Discovery error: {r}")
            continue
        all_found.extend(r)
    
    # Deduplicate by URL
    seen = set()
    unique = []
    for p in all_found:
        if p["url"] not in seen:
            seen.add(p["url"])
            unique.append(p)
    
    logger.info(f"🔍 Discovered {len(unique)} Pokemon TCG products across {len(retailers)} retailers")
    return unique
