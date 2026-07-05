import aiosqlite
from datetime import datetime
from typing import Optional


class Database:
    def __init__(self, path: str):
        self.path = path

    async def init(self):
        async with aiosqlite.connect(self.path) as db:
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id      INTEGER PRIMARY KEY,
                    username     TEXT,
                    balance      INTEGER DEFAULT 0,
                    ref_by       INTEGER,
                    created_at   TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS plans (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    protocol      TEXT NOT NULL DEFAULT 'wg',
                    name          TEXT NOT NULL,
                    duration_days INTEGER NOT NULL,
                    price         INTEGER NOT NULL,
                    active        INTEGER DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS subscriptions (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id      INTEGER NOT NULL,
                    plan_id      INTEGER NOT NULL,
                    protocol     TEXT NOT NULL DEFAULT 'wg',
                    wg_peer_id   TEXT,
                    starts_at    TEXT NOT NULL,
                    expires_at   TEXT NOT NULL,
                    active       INTEGER DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS payments (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     INTEGER NOT NULL,
                    order_id    TEXT UNIQUE,
                    method      TEXT,
                    amount      INTEGER,
                    status      TEXT DEFAULT 'pending',
                    created_at  TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS balance_log (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     INTEGER NOT NULL,
                    delta       INTEGER NOT NULL,
                    reason      TEXT,
                    created_at  TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS promos (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    code        TEXT UNIQUE NOT NULL,
                    bonus       INTEGER NOT NULL,
                    uses_left   INTEGER DEFAULT 1,
                    active      INTEGER DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS promo_uses (
                    user_id     INTEGER,
                    promo_id    INTEGER,
                    PRIMARY KEY (user_id, promo_id)
                );
            """)

            cur = await db.execute("SELECT COUNT(*) FROM plans")
            if (await cur.fetchone())[0] == 0:
                await db.executemany(
                    "INSERT INTO plans (protocol, name, duration_days, price) VALUES (?,?,?,?)",
                    [
                        # WireGuard — дешевле
                        ("wg", "1 месяц",   30,   79),
                        ("wg", "3 месяца",  90,  199),
                        ("wg", "6 месяцев", 180, 349),
                        ("wg", "1 год",     365, 599),
                        # AmneziaWG — дороже, обфускация
                        ("awg", "1 месяц",   30,  129),
                        ("awg", "3 месяца",  90,  329),
                        ("awg", "6 месяцев", 180, 549),
                        ("awg", "1 год",     365, 899),
                    ]
                )
            await db.commit()

    # ── Users ──────────────────────────────────────────────────────────

    async def upsert_user(self, user_id: int, username: str | None, ref_by: int | None = None):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO users (user_id, username, ref_by) VALUES (?,?,?)",
                (user_id, username, ref_by)
            )
            await db.execute("UPDATE users SET username=? WHERE user_id=?", (username, user_id))
            await db.commit()

    async def get_user(self, user_id: int) -> Optional[dict]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
            row = await cur.fetchone()
            return dict(row) if row else None

    async def get_user_count(self) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT COUNT(*) FROM users")
            return (await cur.fetchone())[0]

    async def get_referral_count(self, user_id: int) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT COUNT(*) FROM users WHERE ref_by=?", (user_id,))
            return (await cur.fetchone())[0]

    async def is_new_user(self, user_id: int) -> bool:
        return await self.get_user(user_id) is None

    # ── Balance ────────────────────────────────────────────────────────

    async def change_balance(self, user_id: int, delta: int, reason: str):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE users SET balance = balance + ? WHERE user_id=?",
                (delta, user_id)
            )
            await db.execute(
                "INSERT INTO balance_log (user_id, delta, reason) VALUES (?,?,?)",
                (user_id, delta, reason)
            )
            await db.commit()

    async def try_debit_balance(self, user_id: int, amount: int, reason: str) -> bool:
        """Атомарно списывает amount, только если баланса хватает.

        Возвращает True при успешном списании, False если средств недостаточно.
        Один UPDATE с условием balance >= amount защищает от двойного
        списания при повторных нажатиях кнопки «Оплатить».
        """
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "UPDATE users SET balance = balance - ? "
                "WHERE user_id=? AND balance >= ?",
                (amount, user_id, amount)
            )
            if cur.rowcount == 0:
                return False
            await db.execute(
                "INSERT INTO balance_log (user_id, delta, reason) VALUES (?,?,?)",
                (user_id, -amount, reason)
            )
            await db.commit()
            return True

    # ── Plans ──────────────────────────────────────────────────────────

    async def get_plans_by_protocol(self, protocol: str) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM plans WHERE protocol=? AND active=1 ORDER BY duration_days",
                (protocol,)
            )
            return [dict(r) for r in await cur.fetchall()]

    async def get_plan(self, plan_id: int) -> Optional[dict]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM plans WHERE id=?", (plan_id,))
            row = await cur.fetchone()
            return dict(row) if row else None

    async def get_plans_by_protocol_all(self, protocol: str) -> list[dict]:
        """Все тарифы протокола включая отключённые (для админки)."""
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM plans WHERE protocol=? ORDER BY duration_days",
                (protocol,)
            )
            return [dict(r) for r in await cur.fetchall()]

    async def get_all_plans(self) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM plans ORDER BY protocol, duration_days")
            return [dict(r) for r in await cur.fetchall()]

    async def update_plan_price(self, plan_id: int, price: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE plans SET price=? WHERE id=?", (price, plan_id))
            await db.commit()

    async def toggle_plan(self, plan_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE plans SET active = 1 - active WHERE id=?", (plan_id,))
            await db.commit()

    async def add_plan(self, protocol: str, name: str, duration_days: int, price: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO plans (protocol, name, duration_days, price) VALUES (?,?,?,?)",
                (protocol, name, duration_days, price)
            )
            await db.commit()

    # ── Subscriptions ──────────────────────────────────────────────────

    async def create_subscription(
        self, user_id: int, plan_id: int, protocol: str,
        wg_peer_id: str, starts_at: datetime, expires_at: datetime
    ) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "INSERT INTO subscriptions "
                "(user_id, plan_id, protocol, wg_peer_id, starts_at, expires_at) "
                "VALUES (?,?,?,?,?,?)",
                (user_id, plan_id, protocol, wg_peer_id,
                 starts_at.isoformat(), expires_at.isoformat())
            )
            await db.commit()
            return cur.lastrowid

    async def get_active_subscription(self, user_id: int) -> Optional[dict]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT s.*, p.name as plan_name FROM subscriptions s "
                "JOIN plans p ON p.id=s.plan_id "
                "WHERE s.user_id=? AND s.active=1 ORDER BY s.expires_at DESC LIMIT 1",
                (user_id,)
            )
            row = await cur.fetchone()
            return dict(row) if row else None

    async def get_active_subscription_by_proto(self, user_id: int, protocol: str) -> Optional[dict]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT s.*, p.name as plan_name FROM subscriptions s "
                "JOIN plans p ON p.id=s.plan_id "
                "WHERE s.user_id=? AND s.protocol=? AND s.active=1 "
                "AND s.expires_at > datetime('now') "
                "ORDER BY s.expires_at DESC LIMIT 1",
                (user_id, protocol)
            )
            row = await cur.fetchone()
            return dict(row) if row else None

    async def get_user_subscriptions(self, user_id: int) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT s.*, p.name as plan_name FROM subscriptions s "
                "JOIN plans p ON p.id=s.plan_id "
                "WHERE s.user_id=? ORDER BY s.expires_at DESC LIMIT 10",
                (user_id,)
            )
            return [dict(r) for r in await cur.fetchall()]

    async def get_subscription(self, sub_id: int, user_id: int) -> Optional[dict]:
        """Одна подписка по id с проверкой владельца (для перевыдачи конфига)."""
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT s.*, p.name as plan_name FROM subscriptions s "
                "JOIN plans p ON p.id=s.plan_id "
                "WHERE s.id=? AND s.user_id=?",
                (sub_id, user_id)
            )
            row = await cur.fetchone()
            return dict(row) if row else None

    async def extend_subscription(self, sub_id: int, expires_at: datetime):
        """Продлевает существующую подписку до новой даты (пир не пересоздаётся)."""
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE subscriptions SET expires_at=?, active=1 WHERE id=?",
                (expires_at.isoformat(), sub_id)
            )
            await db.commit()

    async def get_expired_subscriptions(self) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM subscriptions WHERE active=1 AND expires_at < datetime('now')"
            )
            return [dict(r) for r in await cur.fetchall()]

    async def deactivate_subscription(self, sub_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE subscriptions SET active=0 WHERE id=?", (sub_id,))
            await db.commit()

    # ── Payments ───────────────────────────────────────────────────────

    async def create_payment(self, user_id: int, order_id: str, method: str, amount: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO payments (user_id, order_id, method, amount) "
                "VALUES (?,?,?,?)",
                (user_id, order_id, method, amount)
            )
            await db.commit()

    async def get_payment(self, order_id: str) -> Optional[dict]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM payments WHERE order_id=?", (order_id,))
            row = await cur.fetchone()
            return dict(row) if row else None

    async def confirm_payment(self, order_id: str):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE payments SET status='paid' WHERE order_id=?", (order_id,))
            await db.commit()

    async def get_total_revenue(self) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT COALESCE(SUM(amount),0) FROM payments WHERE status='paid'"
            )
            return (await cur.fetchone())[0]

    # ── Promos ─────────────────────────────────────────────────────────

    async def get_promo(self, code: str) -> Optional[dict]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM promos WHERE code=? AND active=1 AND uses_left>0",
                (code.upper(),)
            )
            row = await cur.fetchone()
            return dict(row) if row else None

    async def use_promo(self, user_id: int, promo_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("INSERT INTO promo_uses VALUES (?,?)", (user_id, promo_id))
            await db.execute(
                "UPDATE promos SET uses_left=uses_left-1 WHERE id=?", (promo_id,)
            )
            await db.commit()

    async def has_used_promo(self, user_id: int, promo_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT 1 FROM promo_uses WHERE user_id=? AND promo_id=?",
                (user_id, promo_id)
            )
            return await cur.fetchone() is not None

    async def create_promo(self, code: str, bonus: int, uses: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO promos (code, bonus, uses_left) VALUES (?,?,?)",
                (code.upper(), bonus, uses)
            )
            await db.commit()

    async def get_all_promos(self) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM promos ORDER BY id DESC")
            return [dict(r) for r in await cur.fetchall()]
