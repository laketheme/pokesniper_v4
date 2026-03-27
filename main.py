import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import TELEGRAM_BOT_TOKEN, CHECK_INTERVAL, SCAN_INTERVAL
from database import init_db, list_products, add_product_if_new
from bot import app as telegram_app, setup_handlers, send_restock_alert
from checker import check_all_products, guess_product_type, get_msrp_for_type
from discovery import discover_all_products

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("pokemon_sniper")

scheduler = AsyncIOScheduler()


async def check_cycle():
    """Run one check cycle across all tracked products."""
    try:
        products = await list_products()
        if not products:
            return
        logger.info(f"🔍 Checking {len(products)} Pokemon products across AU retailers...")
        alerts = await check_all_products(products, send_restock_alert)
        if alerts:
            logger.info(f"🚨 Sent {len(alerts)} restock alerts!")
    except Exception as e:
        logger.error(f"Check cycle error: {e}", exc_info=True)


async def auto_scan():
    """Periodically scan all retailers for new products."""
    try:
        logger.info("🔍 Running auto-scan across all AU retailers...")
        discovered = await discover_all_products()
        added = 0
        for p in discovered:
            product_type = guess_product_type(p["name"])
            msrp = get_msrp_for_type(product_type)
            if await add_product_if_new(p["url"], p["name"], p["retailer"],
                                         product_type, msrp, "auto_discovery"):
                added += 1
        if added > 0:
            logger.info(f"🆕 Auto-scan found {added} new products to track!")
        else:
            logger.info("Auto-scan complete, no new products found.")
    except Exception as e:
        logger.error(f"Auto-scan error: {e}", exc_info=True)


@asynccontextmanager
async def lifespan(application: FastAPI):
    logger.info("🎴 Pokemon Card Sniper Bot (AU) starting...")
    await init_db()
    setup_handlers()
    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling(drop_pending_updates=True)

    # Stock checking every N seconds
    scheduler.add_job(check_cycle, "interval", seconds=CHECK_INTERVAL,
                      id="stock_checker", max_instances=1)
    
    # Auto-discovery scan every hour (or configured interval)
    scheduler.add_job(auto_scan, "interval", seconds=SCAN_INTERVAL,
                      id="auto_scanner", max_instances=1)
    
    scheduler.start()
    logger.info(f"✅ Bot running! Stock check every {CHECK_INTERVAL}s, auto-scan every {SCAN_INTERVAL // 60}min")
    
    # Run initial scan on startup
    asyncio.create_task(auto_scan())

    yield

    scheduler.shutdown(wait=False)
    await telegram_app.updater.stop()
    await telegram_app.stop()
    await telegram_app.shutdown()
    logger.info("👋 Bot stopped.")


fastapi_app = FastAPI(title="Pokemon Card Sniper AU", lifespan=lifespan)
app = fastapi_app


@app.get("/health")
async def health():
    products = await list_products()
    return {
        "status": "running",
        "bot": "Pokemon Card Sniper AU",
        "tracking": len(products),
        "stock_interval": f"{CHECK_INTERVAL}s",
        "scan_interval": f"{SCAN_INTERVAL // 60}min",
        "region": "Australia",
    }
