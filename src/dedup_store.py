import asyncio
import logging
import os
import aiosqlite

log = logging.getLogger("dedup")  # dedicated logger

class DedupStore:
    def __init__(self, db_path: str = "data/dedup.db"):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()  # serialize writes

    async def init(self) -> None:
        # init database
        if self._db is not None:
            return
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        await self._db.execute("PRAGMA journal_mode=WAL;")
        await self._db.execute("PRAGMA synchronous=NORMAL;")
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS dedup (
                topic TEXT NOT NULL,
                event_id TEXT NOT NULL,
                PRIMARY KEY (topic, event_id)
            )
        """)
        await self._db.commit()
        log.info("DedupStore initialized at %s", self.db_path)

    async def close(self) -> None:
        # close database
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def mark_if_new(self, topic: str, event_id: str) -> bool:
        # ensure initialized
        if self._db is None:
            raise RuntimeError("DedupStore not initialized")
        async with self._lock:
            try:
                await self._db.execute(
                    "INSERT INTO dedup(topic, event_id) VALUES (?, ?)", (topic, event_id)
                )
                await self._db.commit()
                return True
            except aiosqlite.IntegrityError:
                # duplicate detected
                log.info("duplicate topic=%s event_id=%s", topic, event_id)
                return False
