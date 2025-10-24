import asyncio
import logging
from .state import app_state

log = logging.getLogger("consumer")

# process single event
async def process_event(event: dict) -> None:
    topic = event["topic"]
    event_id = event["event_id"]

    is_new = await app_state.dedup.mark_if_new(topic, event_id)
    if is_new:
        # unique event processed
        app_state.stats.unique_processed += 1
        app_state.events.events_by_topic.setdefault(topic, []).append(event)
        log.debug("unique topic=%s event_id=%s", topic, event_id)
    else:
        # duplicate dropped
        app_state.stats.duplicate_dropped += 1
        log.info("dropped duplicate topic=%s event_id=%s", topic, event_id)

    app_state.stats.processed_total += 1

# main worker loop
async def consumer_loop() -> None:
    while True:
        event: dict = await app_state.queue.get()
        try:
            await process_event(event)
        finally:
            app_state.queue.task_done()
