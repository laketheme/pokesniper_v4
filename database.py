import aiosqlite
import os
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "pokemon_sniper.db")

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                retailer TEXT DEFAULT 'unknown',
                product_type TEXT DEFAULT 'unknown',
                msrp REAL DEFAULT 0,
                last_price REAL DEFAULT 0,
                in_stock INTEGER DEFAULT 0,
                notified INTEGER DEFAULT 0,
                last_checked TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS alerts_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER,
                product_name TEXT,
                url TEXT,
                price REAL,
                retailer TEXT,
                alerted_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

async def add_product(url: str, name: str, retailer: str = "unknown",
                      product_type: str = "unknown", msrp: float = 0) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO products (url, name, retailer, product_type, msrp) VALUES (?, ?, ?, ?, ?)",
                (url, name, retailer, product_type, msrp)
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

async def remove_product(url: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM products WHERE url = ?", (url,))
        await db.commit()
        return cursor.rowcount > 0

async def list_products() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM products ORDER BY retailer, name")
        return [dict(row) for row in await cursor.fetchall()]

async def update_product_status(url: str, in_stock: bool, price: float = 0,
                                 notified: bool = False):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE products
               SET in_stock = ?, last_price = ?, notified = ?, last_checked = ?
               WHERE url = ?""",
            (int(in_stock), price, int(notified), datetime.utcnow().isoformat(), url)
        )
        await db.commit()

async def reset_notification(url: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE products SET notified = 0 WHERE url = ?", (url,))
        await db.commit()

async def log_alert(product_id: int, name: str, url: str, price: float, retailer: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO alerts_log (product_id, product_name, url, price, retailer) VALUES (?, ?, ?, ?, ?)",
            (product_id, name, url, price, retailer)
        )
        await db.commit()

async def get_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM products")
        total = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT COUNT(*) FROM products WHERE in_stock = 1")
        in_stock = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT COUNT(*) FROM alerts_log")
        total_alerts = (await cursor.fetchone())[0]
        cursor = await db.execute(
            "SELECT COUNT(*) FROM alerts_log WHERE alerted_at > datetime('now', '-24 hours')"
        )
        alerts_24h = (await cursor.fetchone())[0]
        return {
            "total_products": total,
            "in_stock": in_stock,
            "total_alerts": total_alerts,
            "alerts_24h": alerts_24h,
        }
