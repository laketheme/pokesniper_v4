import asyncio
import aiohttp
import re
import json
import logging
from datetime import datetime
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from config import MAX_CONCURRENT, POKEMON_MSRP_AUD, MSRP_TOLERANCE, AU_RETAILERS
from database import update_product_status, reset_notification, log_alert

logger = logging.getLogger("pokemon_sniper")
ua = UserAgent()
semaphore = asyncio.Semaphore(MAX_CONCURRENT)

IN_STOCK_PATTERNS = [
    re.compile(r"add[- _]?to[- _]?cart", re.IGNORECASE),
    re.compile(r"add[- _]?to[- _]?bag", re.IGNORECASE),
    re.compile(r"in[- _]?stock", re.IGNORECASE),
    re.compile(r'"availability"\s*:\s*"https?://schema\.org/InStock"', re.IGNORECASE),
    re.compile(r"available\s+online", re.IGNORECASE),
    re.compile(r"buy\s+now", re.IGNORECASE),
]

OUT_OF_STOCK_PATTERNS = [
    re.compile(r"out[- _]?of[- _]?stock", re.IGNORECASE),
    re.compile(r"sold[- _]?out", re.IGNORECASE),
    re.compile(r"currently[- _]?unavailable", re.IGNORECASE),
    re.compile(r"not[- _]?available", re.IGNORECASE),
    re.compile(r"coming[- _]?soon", re.IGNORECASE),
    re.compile(r"pre[- _]?order", re.IGNORECASE),
    re.compile(r"notify[- _]?me", re.IGNORECASE),
    re.compile(r"back[- _]?order", re.IGNORECASE),
]

PRICE_PATTERNS = [
    re.compile(r'\$\s?(\d+[.,]\d{2})', re.IGNORECASE),
    re.compile(r'"price"\s*:\s*"?(\d+\.?\d*)"?', re.IGNORECASE),
    re.compile(r'data-price="(\d+\.?\d*)"', re.IGNORECASE),
]


def get_headers():
    return {
        "User-Agent": ua.random,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-AU,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",
    }


def detect_retailer(url: str) -> str:
    url_lower = url.lower()
    for key, info in AU_RETAILERS.items():
        if info["base_url"].replace("https://", "").replace("www.", "") in url_lower:
            return key
    return "unknown"


def guess_product_type(name: str) -> str:
    name_lower = name.lower()
    type_map = {
        "elite trainer box": "elite_trainer_box",
        "etb": "elite_trainer_box",
        "booster box": "booster_box",
        "booster bundle": "booster_bundle",
        "booster pack": "booster_pack",
        "ultra premium": "ultra_premium_collection",
        "premium collection": "premium_collection",
        "collection box": "collection_box",
        "3 pack": "blister_3pack",
        "3-pack": "blister_3pack",
        "blister": "blister_1pack",
        "tin": "tin",
        "build & battle stadium": "build_battle_stadium",
        "build & battle box": "build_battle_box",
        "build and battle": "build_battle_box",
        "poster collection": "poster_collection",
        "binder collection": "binder_collection",
        "special illustration": "special_illustration_collection",
    }
    for keyword, ptype in type_map.items():
        if keyword in name_lower:
            return ptype
    return "unknown"


def get_msrp_for_type(product_type: str) -> float:
    return POKEMON_MSRP_AUD.get(product_type, 0)


def is_at_msrp(price: float, product_type: str, custom_msrp: float = 0) -> bool:
    msrp = custom_msrp if custom_msrp > 0 else get_msrp_for_type(product_type)
    if msrp <= 0:
        return True  # no MSRP data, allow alert
    return price <= msrp * MSRP_TOLERANCE


async def check_shopify_product(session: aiohttp.ClientSession, url: str) -> dict:
    """Check Shopify-based stores via their JSON API."""
    json_url = url.rstrip("/") + ".json"
    try:
        async with session.get(json_url, headers=get_headers(), timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                data = await resp.json()
                product = data.get("product", {})
                variants = product.get("variants", [])
                available = any(v.get("available", False) for v in variants)
                prices = [float(v.get("price", "0")) for v in variants if v.get("available")]
                price = min(prices) if prices else 0
                return {"in_stock": available, "price": price, "method": "shopify_api"}
    except Exception as e:
        logger.debug(f"Shopify JSON failed for {url}: {e}")

    # Fallback: try /products.json search
    return {"in_stock": None, "price": 0, "method": "failed"}


async def check_html_product(session: aiohttp.ClientSession, url: str) -> dict:
    """Check stock via HTML scraping with pattern matching."""
    try:
        async with session.get(url, headers=get_headers(), timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return {"in_stock": None, "price": 0, "method": "http_error"}
            html = await resp.text()
    except Exception as e:
        logger.error(f"HTML fetch failed for {url}: {e}")
        return {"in_stock": None, "price": 0, "method": "fetch_error"}

    # Check for out-of-stock first (takes priority)
    for pattern in OUT_OF_STOCK_PATTERNS:
        if pattern.search(html):
            # Extract price anyway
            price = extract_price(html)
            return {"in_stock": False, "price": price, "method": "html_oos_pattern"}

    # Check for in-stock signals
    for pattern in IN_STOCK_PATTERNS:
        if pattern.search(html):
            price = extract_price(html)
            return {"in_stock": True, "price": price, "method": "html_in_stock_pattern"}

    # Check JSON-LD structured data
    soup = BeautifulSoup(html, "lxml")
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            ld = json.loads(script.string)
            items = ld if isinstance(ld, list) else [ld]
            for item in items:
                if item.get("@type") == "Product":
                    offers = item.get("offers", {})
                    if isinstance(offers, list):
                        offers = offers[0] if offers else {}
                    avail = offers.get("availability", "")
                    price = float(offers.get("price", 0))
                    in_stock = "InStock" in avail
                    return {"in_stock": in_stock, "price": price, "method": "json_ld"}
        except (json.JSONDecodeError, ValueError, KeyError):
            continue

    price = extract_price(html)
    return {"in_stock": None, "price": price, "method": "unknown"}


def extract_price(html: str) -> float:
    for pattern in PRICE_PATTERNS:
        match = pattern.search(html)
        if match:
            try:
                return float(match.group(1).replace(",", "."))
            except ValueError:
                continue
    return 0


async def check_product(session: aiohttp.ClientSession, product: dict) -> dict:
    """Check a single product with retry logic."""
    url = product["url"]
    retailer = product.get("retailer", detect_retailer(url))
    retailer_info = AU_RETAILERS.get(retailer, {})
    store_type = retailer_info.get("type", "html")

    result = None
    for attempt in range(3):
        try:
            async with semaphore:
                if store_type == "shopify":
                    result = await check_shopify_product(session, url)
                    if result["in_stock"] is None:
                        result = await check_html_product(session, url)
                else:
                    result = await check_html_product(session, url)

                if result["in_stock"] is not None:
                    break
        except Exception as e:
            logger.error(f"Attempt {attempt + 1} failed for {url}: {e}")
            await asyncio.sleep(2 ** attempt)

    if result is None:
        result = {"in_stock": None, "price": 0, "method": "all_failed"}

    return {**result, "product": product}


async def check_all_products(products: list, send_alert_fn) -> list:
    """Check all products concurrently and send alerts for MSRP restocks."""
    if not products:
        return []

    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [check_product(session, p) for p in products]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    alerts_sent = []
    for r in results:
        if isinstance(r, Exception):
            logger.error(f"Check failed with exception: {r}")
            continue

        product = r["product"]
        in_stock = r.get("in_stock")
        price = r.get("price", 0)

        if in_stock is None:
            continue

        was_in_stock = bool(product.get("in_stock", 0))
        was_notified = bool(product.get("notified", 0))
        product_type = product.get("product_type", "unknown")
        custom_msrp = product.get("msrp", 0)

        if in_stock:
            at_msrp = is_at_msrp(price, product_type, custom_msrp)

            if not was_in_stock and not was_notified and at_msrp:
                # RESTOCK at MSRP detected!
                msrp_val = custom_msrp if custom_msrp > 0 else get_msrp_for_type(product_type)
                retailer_name = AU_RETAILERS.get(product.get("retailer", ""), {}).get("name", product.get("retailer", "Unknown"))
                await send_alert_fn(product, price, retailer_name, msrp_val)
                await update_product_status(product["url"], True, price, True)
                await log_alert(product["id"], product["name"], product["url"], price, retailer_name)
                alerts_sent.append(product)
                logger.info(f"🚨 ALERT: {product['name']} IN STOCK at ${price:.2f} AUD @ {retailer_name}")
            elif not at_msrp:
                await update_product_status(product["url"], True, price, False)
                logger.info(f"⚠️ {product['name']} in stock but ABOVE MSRP: ${price:.2f} (MSRP: ${msrp_val:.2f})")
            else:
                await update_product_status(product["url"], True, price, was_notified)
        else:
            if was_in_stock:
                await reset_notification(product["url"])
                logger.info(f"📦 {product['name']} went OUT OF STOCK — notification reset")
            await update_product_status(product["url"], False, price, False)

    return alerts_sent
