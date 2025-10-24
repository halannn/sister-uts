import asyncio, random, time, argparse, os
import httpx
from datetime import datetime, timezone

def make_event(topic: str, eid: str, src="bench", payload=None):
    return {
        "topic": topic,
        "event_id": eid,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": src,
        "payload": payload or {},
    }

async def publish_batch(client: httpx.AsyncClient, url: str, batch):
    r = await client.post(url, json={"events": batch}, timeout=30.0)
    r.raise_for_status()
    return r.json()

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.getenv("AGG_URL", "http://localhost:8080/publish"))
    ap.add_argument("--topic", default="bench")
    ap.add_argument("--count", type=int, default=int(os.getenv("COUNT", "5000")))
    ap.add_argument("--unique", type=int, default=int(os.getenv("UNIQUE", "4000")))  # >=20% dupe: 5k total, 4k unik → 20% dupe
    ap.add_argument("--batch", type=int, default=int(os.getenv("BATCH", "500")))
    ap.add_argument("--concurrency", type=int, default=int(os.getenv("CONC", "4")))
    args = ap.parse_args()

    assert args.unique <= args.count, "unique must be <= count"

    ids = [f"id{i}" for i in range(args.unique)]
    events = []
    for i in range(args.count):
        if i < args.unique:
            eid = ids[i]
        else:
            eid = random.choice(ids)
        events.append(make_event(args.topic, eid))

    batches = [events[i:i+args.batch] for i in range(0, len(events), args.batch)]

    sem = asyncio.Semaphore(args.concurrency)
    async with httpx.AsyncClient() as client:
        start = time.time()
        async def worker(batch):
            async with sem:
                return await publish_batch(client, args.url, batch)

        await asyncio.gather(*(worker(b) for b in batches))
        elapsed = time.time() - start

        stats = (await client.get(args.url.replace("/publish", "/stats"))).json()
        print("\n=== Benchmark Result ===")
        print(f"sent_total={args.count} unique_target={args.unique}")
        print(f"received={stats['received']} unique_processed={stats['unique_processed']} dup_dropped={stats['duplicate_dropped']}")
        print(f"elapsed_sec={elapsed:.3f} throughput_eps≈{args.count/elapsed:.1f}")

if __name__ == "__main__":
    asyncio.run(main())
