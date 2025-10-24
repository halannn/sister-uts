import asyncio
import logging
from contextlib import suppress, asynccontextmanager
from time import monotonic

from fastapi import FastAPI, status, Body

from .models import PublishRequest
from .state import app_state, Stats, InMemoryEventStore
from .dedup_store import DedupStore
from .consumer import consumer_loop
from .config import settings as global_settings

logging.basicConfig(
    level=logging.getLevelName("INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("aggregator")

CONSUMER_WORKERS = 4
ENQUEUE_WAIT_TIMEOUT = 2.0
POLL_INTERVAL = 0.005

# reset in-memory state
def _reset_state() -> None:
    app_state.queue = asyncio.Queue()
    app_state.stats = Stats()
    app_state.events = InMemoryEventStore()
    app_state.consumer_tasks = []

# open dedup store
async def _ensure_dedup() -> None:
    if app_state.dedup is None:
        db_path = app_state.fallback_db_path or global_settings.dedup_db_path
        app_state.dedup = DedupStore(db_path=db_path)
        await app_state.dedup.init()

# start consumers
def _start_consumers(n: int = CONSUMER_WORKERS) -> None:
    app_state.consumer_tasks = [asyncio.create_task(consumer_loop()) for _ in range(n)]
    log.info("Consumers started (%d).", n)

# stop consumers
async def _stop_consumers() -> None:
    for t in app_state.consumer_tasks:
        t.cancel()
    for t in app_state.consumer_tasks:
        with suppress(asyncio.CancelledError):
            await t
    app_state.consumer_tasks.clear()

# process synchronously
async def _process_events_sync(events: list[dict]) -> None:
    for ev in events:
        is_new = await app_state.dedup.mark_if_new(ev["topic"], ev["event_id"])
        if is_new:
            app_state.stats.unique_processed += 1
            app_state.events.events_by_topic.setdefault(ev["topic"], []).append(ev)
        else:
            app_state.stats.duplicate_dropped += 1
        app_state.stats.processed_total += 1

# enqueue and wait
async def _enqueue_and_wait(events: list[dict], timeout: float) -> None:
    base = app_state.stats.processed_total
    for ev in events:
        app_state.queue.put_nowait(ev)
    target = base + len(events)
    try:
        async with asyncio.timeout(timeout):
            while app_state.stats.processed_total < target:
                await asyncio.sleep(POLL_INTERVAL)
    except asyncio.TimeoutError:
        pass

def create_app(dedup_db_path: str | None = None) -> FastAPI:
    # init fallback path
    app_state.fallback_db_path = dedup_db_path or global_settings.dedup_db_path

    # lifespan: setup and teardown
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        _reset_state()
        await _ensure_dedup()
        _start_consumers()
        log.info("DB=%s", app_state.dedup.db_path if app_state.dedup else "-")
        try:
            yield
        finally:
            await _stop_consumers()
            if app_state.dedup:
                await app_state.dedup.close()
            app_state.dedup = None
            log.info("Consumers stopped and DB closed.")

    app = FastAPI(title="Aggregator", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    # POST publish
    @app.post("/publish", status_code=status.HTTP_202_ACCEPTED)
    async def publish(req: PublishRequest = Body(...)):
        events = [ev.model_dump() for ev in req.events]
        app_state.stats.received += len(events)

        # ensure dedup exists
        await _ensure_dedup()

        if not app_state.consumer_tasks:
            await _process_events_sync(events)
            return {"processed_sync": len(events)}

        await _enqueue_and_wait(events, ENQUEUE_WAIT_TIMEOUT)
        return {"enqueued": len(events)}

    @app.get("/stats")
    async def stats():
        # build stats
        uptime = monotonic() - app_state.stats.started_at_monotonic
        topics = sorted(app_state.events.events_by_topic.keys())
        return {
            "received": app_state.stats.received,
            "unique_processed": app_state.stats.unique_processed,
            "duplicate_dropped": app_state.stats.duplicate_dropped,
            "processed_total": app_state.stats.processed_total,
            "topics": list(topics),
            "uptime_seconds": round(uptime, 3),
            "queue_size": app_state.queue.qsize(),
        }

    @app.get("/events")
    async def list_events(topic: str | None = None):
        # list events
        if topic:
            return app_state.events.events_by_topic.get(topic, [])
        return {t: len(v) for t, v in app_state.events.events_by_topic.items()}

    return app
