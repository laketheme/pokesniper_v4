import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "15"))
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "3600"))  # auto-scan every hour
MAX_CONCURRENT = 10

# Modern Pokemon TCG sets (most recent first) — update as new sets release
MODERN_SETS = [
    # 2025
    "Prismatic Evolutions",
    "Journey Together",
    "Destined Rivals",
    "Shining Revelations",
    # 2024
    "Surging Sparks",
    "Stellar Crown",
    "Shrouded Fable",
    "Twilight Masquerade",
    "Temporal Forces",
    "Paldean Fates",
    # 2023 (still widely stocked)
    "Paradox Rift",
    "151",
    "Obsidian Flames",
    "Paldea Evolved",
    "Scarlet & Violet",
    # Special products that span sets
    "Trainer Gallery",
    "Special Illustration",
    "Crown Zenith",
]

# Australian Pokemon card retailers with known product pages
AU_RETAILERS = {
    "pokemoncenter_au": {
        "name": "Pokemon Center AU",
        "base_url": "https://www.pokemoncenter.com.au",
        "search_url": "https://www.pokemoncenter.com.au/collections/trading-card-game",
        "type": "shopify",
        "currency": "AUD",
    },
    "eb_games": {
        "name": "EB Games Australia",
        "base_url": "https://www.ebgames.com.au",
        "search_url": "https://www.ebgames.com.au/search?q=pokemon+cards",
        "type": "html",
        "currency": "AUD",
    },
    "gameology": {
        "name": "Gameology",
        "base_url": "https://www.gameology.com.au",
        "search_url": "https://www.gameology.com.au/collections/pokemon",
        "type": "shopify",
        "currency": "AUD",
    },
    "good_games": {
        "name": "Good Games AU",
        "base_url": "https://www.goodgames.com.au",
        "search_url": "https://www.goodgames.com.au/trading-card-games/pokemon.html",
        "type": "html",
        "currency": "AUD",
    },
    "jbhifi": {
        "name": "JB Hi-Fi",
        "base_url": "https://www.jbhifi.com.au",
        "search_url": "https://www.jbhifi.com.au/search?q=pokemon+cards",
        "type": "html",
        "currency": "AUD",
    },
    "big_w": {
        "name": "Big W",
        "base_url": "https://www.bigw.com.au",
        "search_url": "https://www.bigw.com.au/search?q=pokemon+cards",
        "type": "html",
        "currency": "AUD",
    },
    "target_au": {
        "name": "Target Australia",
        "base_url": "https://www.target.com.au",
        "search_url": "https://www.target.com.au/search?text=pokemon+cards",
        "type": "html",
        "currency": "AUD",
    },
    "zing_pop": {
        "name": "Zing Pop Culture",
        "base_url": "https://www.zingpopculture.com.au",
        "search_url": "https://www.zingpopculture.com.au/search?q=pokemon+cards",
        "type": "html",
        "currency": "AUD",
    },
    "toymate": {
        "name": "Toymate",
        "base_url": "https://www.toymate.com.au",
        "search_url": "https://www.toymate.com.au/search?q=pokemon+cards",
        "type": "html",
        "currency": "AUD",
    },
    "mightyape": {
        "name": "Mighty Ape AU",
        "base_url": "https://www.mightyape.com.au",
        "search_url": "https://www.mightyape.com.au/search?q=pokemon+tcg",
        "type": "html",
        "currency": "AUD",
    },
}

# Known MSRP prices in AUD for common Pokemon TCG products
POKEMON_MSRP_AUD = {
    "booster_pack": 6.95,
    "booster_bundle": 34.95,
    "elite_trainer_box": 79.95,
    "booster_box": 215.00,
    "collection_box": 39.95,
    "premium_collection": 69.95,
    "ultra_premium_collection": 179.95,
    "blister_3pack": 16.95,
    "blister_1pack": 7.95,
    "tin": 34.95,
    "build_battle_stadium": 64.95,
    "build_battle_box": 29.95,
    "poster_collection": 34.95,
    "binder_collection": 29.95,
    "special_illustration_collection": 49.95,
}

# Price thresholds — alert only if price <= MSRP * multiplier
MSRP_TOLERANCE = 1.05  # allow 5% above MSRP
