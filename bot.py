import logging
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes
from config import TELEGRAM_BOT_TOKEN, CHAT_ID, POKEMON_MSRP_AUD, AU_RETAILERS, MODERN_SETS
from database import (add_product, remove_product, list_products, get_stats,
                      add_product_if_new, get_discovery_count)
from checker import detect_retailer, guess_product_type, get_msrp_for_type
from discovery import discover_all_products, is_pokemon_tcg_product

logger = logging.getLogger("pokemon_sniper")

app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎴 <b>Pokemon Card Sniper Bot (AU)</b>\n\n"
        "I automatically find & monitor Australian retailers for Pokemon TCG restocks at MSRP.\n\n"
        "<b>Commands:</b>\n"
        "/scan — Auto-discover products from all AU retailers\n"
        "/scanretailer &lt;name&gt; — Scan a specific retailer\n"
        "/sets — Show tracked modern sets\n"
        "/add &lt;url&gt; &lt;name&gt; — Manually track a product\n"
        "/addmsrp &lt;url&gt; &lt;msrp&gt; &lt;name&gt; — Track with custom MSRP\n"
        "/remove &lt;url&gt; — Stop tracking\n"
        "/list — Show all tracked products\n"
        "/retailers — Show supported AU retailers\n"
        "/msrp — Show known MSRP prices\n"
        "/status — Bot stats\n"
        "/help — This message",
        parse_mode="HTML"
    )


async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Auto-discover Pokemon TCG products across all AU retailers."""
    msg = await update.message.reply_text(
        "🔍 <b>Scanning all AU retailers for Pokemon TCG products...</b>\n"
        "This may take 30-60 seconds.",
        parse_mode="HTML"
    )
    
    try:
        discovered = await discover_all_products()
        added = 0
        skipped = 0
        
        for p in discovered:
            product_type = guess_product_type(p["name"])
            msrp = get_msrp_for_type(product_type)
            was_added = await add_product_if_new(
                url=p["url"],
                name=p["name"],
                retailer=p["retailer"],
                product_type=product_type,
                msrp=msrp,
                source="auto_discovery"
            )
            if was_added:
                added += 1
            else:
                skipped += 1
        
        # Group by retailer for summary
        by_retailer = {}
        for p in discovered:
            rname = AU_RETAILERS.get(p["retailer"], {}).get("name", p["retailer"])
            by_retailer[rname] = by_retailer.get(rname, 0) + 1
        
        retailer_summary = "\n".join(
            f"  • {name}: {count} products" for name, count in sorted(by_retailer.items())
        )
        
        await msg.edit_text(
            f"✅ <b>Scan Complete!</b>\n\n"
            f"🔍 Found: {len(discovered)} Pokemon TCG products\n"
            f"➕ New: {added} added to tracking\n"
            f"⏭️ Already tracked: {skipped}\n\n"
            f"<b>By Retailer:</b>\n{retailer_summary}\n\n"
            f"All new products will be checked every 15s for restocks!",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Scan failed: {e}", exc_info=True)
        await msg.edit_text(f"❌ Scan failed: {str(e)[:200]}")


async def cmd_scanretailer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scan a specific retailer."""
    if not context.args:
        retailer_list = "\n".join(f"  • <code>{k}</code> — {v['name']}" 
                                   for k, v in AU_RETAILERS.items())
        await update.message.reply_text(
            f"Usage: /scanretailer <retailer_key>\n\n"
            f"Available retailers:\n{retailer_list}",
            parse_mode="HTML"
        )
        return
    
    target = context.args[0].lower()
    if target not in AU_RETAILERS:
        await update.message.reply_text(f"❌ Unknown retailer: {target}\nUse /scanretailer to see options.")
        return
    
    rname = AU_RETAILERS[target]["name"]
    msg = await update.message.reply_text(f"🔍 Scanning <b>{rname}</b>...", parse_mode="HTML")
    
    try:
        discovered = await discover_all_products(target_retailers=[target])
        added = 0
        for p in discovered:
            product_type = guess_product_type(p["name"])
            msrp = get_msrp_for_type(product_type)
            if await add_product_if_new(p["url"], p["name"], p["retailer"],
                                         product_type, msrp, "auto_discovery"):
                added += 1
        
        await msg.edit_text(
            f"✅ <b>{rname} Scan Complete!</b>\n\n"
            f"🔍 Found: {len(discovered)} products\n"
            f"➕ New: {added} added to tracking",
            parse_mode="HTML"
        )
    except Exception as e:
        await msg.edit_text(f"❌ Scan failed: {str(e)[:200]}")


async def cmd_sets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the modern sets being tracked."""
    sets_2025 = [s for s in MODERN_SETS if MODERN_SETS.index(s) < 4]
    sets_2024 = [s for s in MODERN_SETS if 4 <= MODERN_SETS.index(s) < 10]
    sets_2023 = [s for s in MODERN_SETS if 10 <= MODERN_SETS.index(s) < 15]
    special = [s for s in MODERN_SETS if MODERN_SETS.index(s) >= 15]
    
    msg = "🎴 <b>Modern Sets Being Tracked:</b>\n\n"
    msg += "<b>🔥 2025:</b>\n" + "\n".join(f"  • {s}" for s in sets_2025) + "\n\n"
    msg += "<b>⭐ 2024:</b>\n" + "\n".join(f"  • {s}" for s in sets_2024) + "\n\n"
    msg += "<b>📦 2023:</b>\n" + "\n".join(f"  • {s}" for s in sets_2023) + "\n\n"
    if special:
        msg += "<b>✨ Special:</b>\n" + "\n".join(f"  • {s}" for s in special) + "\n"
    
    msg += "\n💡 The bot auto-discovers products from these sets across all AU retailers."
    await update.message.reply_text(msg, parse_mode="HTML")


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /add <url> <product name>\n"
            "Example: /add https://www.ebgames.com.au/product/pokemon-etb Pokemon SV8 ETB"
        )
        return

    url = context.args[0]
    name = " ".join(context.args[1:])
    retailer = detect_retailer(url)
    product_type = guess_product_type(name)
    msrp = get_msrp_for_type(product_type)
    retailer_name = AU_RETAILERS.get(retailer, {}).get("name", retailer)

    success = await add_product(url, name, retailer, product_type, msrp)
    if success:
        msg = (
            f"✅ <b>Now tracking:</b>\n"
            f"📦 {name}\n"
            f"🏪 {retailer_name}\n"
            f"📋 Type: {product_type.replace('_', ' ').title()}\n"
        )
        if msrp > 0:
            msg += f"💰 MSRP: ${msrp:.2f} AUD\n"
        msg += f"🔗 {url}"
        await update.message.reply_text(msg, parse_mode="HTML")
    else:
        await update.message.reply_text("⚠️ Already tracking this URL.")


async def cmd_addmsrp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or len(context.args) < 3:
        await update.message.reply_text(
            "Usage: /addmsrp <url> <msrp_price> <product name>\n"
            "Example: /addmsrp https://example.com/etb 79.95 Pokemon SV8 ETB"
        )
        return

    url = context.args[0]
    try:
        msrp = float(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Invalid MSRP price. Use a number like 79.95")
        return

    name = " ".join(context.args[2:])
    retailer = detect_retailer(url)
    product_type = guess_product_type(name)

    success = await add_product(url, name, retailer, product_type, msrp)
    if success:
        retailer_name = AU_RETAILERS.get(retailer, {}).get("name", retailer)
        await update.message.reply_text(
            f"✅ <b>Now tracking (custom MSRP):</b>\n"
            f"📦 {name}\n"
            f"🏪 {retailer_name}\n"
            f"💰 MSRP: ${msrp:.2f} AUD\n"
            f"🔗 {url}",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text("⚠️ Already tracking this URL.")


async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /remove <url>")
        return
    url = context.args[0]
    success = await remove_product(url)
    if success:
        await update.message.reply_text(f"🗑️ Removed: {url}")
    else:
        await update.message.reply_text("❌ URL not found in tracking list.")


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    products = await list_products()
    if not products:
        await update.message.reply_text(
            "📭 No products being tracked.\n"
            "Use /scan to auto-discover products, or /add to manually add one!"
        )
        return

    # Split into chunks if too many
    chunks = []
    msg = "🎴 <b>Tracked Pokemon Products:</b>\n\n"
    for i, p in enumerate(products, 1):
        stock = "🟢 IN" if p["in_stock"] else "🔴 OOS"
        retailer_name = AU_RETAILERS.get(p.get("retailer", ""), {}).get("name", p.get("retailer", "?"))
        price_str = f"${p['last_price']:.2f}" if p.get("last_price", 0) > 0 else "—"
        source_icon = "🤖" if p.get("source") == "auto_discovery" else "👤"

        entry = f"{source_icon} <b>{p['name'][:60]}</b>\n   {stock} | {price_str} | {retailer_name}\n\n"
        
        if len(msg) + len(entry) > 3800:
            chunks.append(msg)
            msg = ""
        msg += entry
    
    if msg:
        chunks.append(msg)
    
    for chunk in chunks:
        await update.message.reply_text(chunk, parse_mode="HTML", disable_web_page_preview=True)


async def cmd_retailers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "🏪 <b>Supported AU Retailers:</b>\n\n"
    for key, info in AU_RETAILERS.items():
        msg += f"• <b>{info['name']}</b> ({info['type'].upper()})\n  <code>{key}</code>\n\n"
    msg += "Use /scan to auto-discover products from all retailers!\nUse /scanretailer <code>key</code> to scan one."
    await update.message.reply_text(msg, parse_mode="HTML", disable_web_page_preview=True)


async def cmd_msrp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "💰 <b>Known Pokemon TCG MSRP (AUD):</b>\n\n"
    for ptype, price in sorted(POKEMON_MSRP_AUD.items(), key=lambda x: x[1]):
        msg += f"• {ptype.replace('_', ' ').title()}: <b>${price:.2f}</b>\n"
    msg += f"\n⚙️ Alert threshold: MSRP × 1.05 (5% tolerance)"
    await update.message.reply_text(msg, parse_mode="HTML")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = await get_stats()
    auto_count = await get_discovery_count()
    from config import CHECK_INTERVAL, SCAN_INTERVAL
    await update.message.reply_text(
        f"📊 <b>Pokemon Sniper Status</b>\n\n"
        f"📦 Products tracked: {stats['total_products']}\n"
        f"   🤖 Auto-discovered: {auto_count}\n"
        f"   👤 Manual: {stats['total_products'] - auto_count}\n"
        f"🟢 Currently in stock: {stats['in_stock']}\n"
        f"🔔 Total alerts sent: {stats['total_alerts']}\n"
        f"📬 Alerts (24h): {stats['alerts_24h']}\n"
        f"⏱️ Stock check: every {CHECK_INTERVAL}s\n"
        f"🔍 Auto-scan: every {SCAN_INTERVAL // 60}min\n"
        f"🌏 Region: Australia\n"
        f"💱 Currency: AUD\n"
        f"📋 Sets tracked: {len(MODERN_SETS)}",
        parse_mode="HTML"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, context)


def setup_handlers():
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("scan", cmd_scan))
    app.add_handler(CommandHandler("scanretailer", cmd_scanretailer))
    app.add_handler(CommandHandler("sets", cmd_sets))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("addmsrp", cmd_addmsrp))
    app.add_handler(CommandHandler("remove", cmd_remove))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("retailers", cmd_retailers))
    app.add_handler(CommandHandler("msrp", cmd_msrp))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("help", cmd_help))


async def send_restock_alert(product: dict, price: float, retailer_name: str, msrp: float):
    from datetime import datetime
    price_str = f"${price:.2f}" if price > 0 else "Price unknown"
    msrp_str = f"${msrp:.2f}" if msrp > 0 else "N/A"

    if price > 0 and msrp > 0:
        savings = msrp - price
        savings_str = f"\n💸 {'Savings' if savings >= 0 else 'Over MSRP'}: ${abs(savings):.2f}"
    else:
        savings_str = ""

    source_str = " (auto-found)" if product.get("source") == "auto_discovery" else ""

    msg = (
        f"🚨🎴 <b>POKEMON CARD RESTOCK!</b> 🎴🚨\n\n"
        f"📦 <b>{product['name']}</b>{source_str}\n"
        f"🏪 {retailer_name}\n"
        f"💰 Price: <b>{price_str} AUD</b>\n"
        f"📋 MSRP: {msrp_str} AUD{savings_str}\n"
        f"🕐 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
        f"🔗 <a href=\"{product['url']}\">BUY NOW →</a>\n\n"
        f"⚡ <i>Go go go! Pokemon cards sell out fast!</i>"
    )
    try:
        await app.bot.send_message(
            chat_id=CHAT_ID, text=msg, parse_mode="HTML",
            disable_web_page_preview=False
        )
    except Exception as e:
        logger.error(f"Failed to send alert: {e}")
