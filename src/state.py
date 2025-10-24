import asyncio
from dataclasses import dataclass, field
from time import monotonic
from typing import Dict, List

# metrics counters
@dataclass
class Stats:
    received: int = 0
    unique_processed: int = 0
    duplicate_dropped: int = 0
    processed_total: int = 0
    started_at_monotonic: float = field(default_factory=monotonic)

# in-memory store
@dataclass
class InMemoryEventStore:
    events_by_topic: Dict[str, List[dict]] = field(default_factory=dict)

# application state container
class AppState:
    def __init__(self):
        self.queue: asyncio.Queue[dict] = asyncio.Queue()
        self.stats = Stats()
        self.events = InMemoryEventStore()
        self.dedup = None
        self.consumer_tasks: list[asyncio.Task] = []
        self.fallback_db_path: str | None = None

    def reset(self) -> None:
        # reset all runtime state
        self.queue = asyncio.Queue()
        self.stats = Stats()
        self.events = InMemoryEventStore()
        self.consumer_tasks = []

# global app state
app_state = AppState()
