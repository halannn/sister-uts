import asyncio
import argparse
import json
import random
import string
import time
from typing import List, Dict
import httpx

def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def rand_str(n=6):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))

def gen_events(total: int, dup_ratio: float, topic: str, run_id: str) -> List[Dict]:
    uniq = int(total * (1 - dup_ratio))
    dups = total - uniq
    base = []
    for i in range(uniq):
        eid = f"{run_id}-{i}"
        base.append({
            "topic": topic,
            "event_id": eid,
            "timestamp": now_iso(),
            "source": "perf",
            "payload": {"i": i}
        })
    # ambil duplikasi dari base (dengan pengulangan)
    dup_events = [dict(base[idx]) for idx in random.choices(range(uniq), k=dups)]
    events = base + dup_events
    random.shuffle(events)
    return events

def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

def percentiles(samples, ps):
    if not samples:
        return {p: None for p in ps}
    s = sorted(samples)
    res = {}
    for p in ps:
        k = max(0, min(len(s) - 1, int(round(p/100 * (len(s)-1)))))
        res[p] = s[k]
    return res

async def post_batch(client: httpx.AsyncClient, url: str, events: List[Dict]) -> float:
    t0 = time.perf_counter()
    r = await client.post(url, json={"events": events}, timeout=15.0)
    r.raise_for_status()
    return (time.perf_counter() - t0) * 1000.0

async def ping_health(client: httpx.AsyncClient, url: str, stop: asyncio.Event, samples: List[float]):
    while not stop.is_set():
        t0 = time.perf_counter()
        try:
            r = await client.get(url, timeout=5.0)
            if r.status_code == 200:
                samples.append((time.perf_counter() - t0) * 1000.0)
        except Exception:
            samples.append(5000.0)  # timeout/error sentinel
        await asyncio.sleep(0.2)

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-s", "--server", default="http://localhost:8080")
    ap.add_argument("-n", "--total", type=int, default=5000)
    ap.add_argument("-d", "--dup-ratio", type=float, default=0.25)  # 25% duplikasi
    ap.add_argument("-b", "--batch-size", type=int, default=100)
    ap.add_argument("-c", "--concurrency", type=int, default=10)
    ap.add_argument("-t", "--topic", default="perf")
    args = ap.parse_args()

    run_id = f"run{int(time.time())}-{rand_str(4)}"
    events = gen_events(args.total, args.dup_ratio, args.topic, run_id)
    batches = list(chunks(events, args.batch_size))

    publish_url = f"{args.server}/publish"
    stats_url = f"{args.server}/stats"
    health_url = f"{args.server}/health"

    limits = httpx.Limits(max_connections=args.concurrency, max_keepalive_connections=args.concurrency)
    async with httpx.AsyncClient(limits=limits) as client:
        stop = asyncio.Event()
        health_samples: List[float] = []
        health_task = asyncio.create_task(ping_health(client, health_url, stop, health_samples))

        sem = asyncio.Semaphore(args.concurrency)
        lat_samples: List[float] = []

        async def worker(batch):
            async with sem:
                lat = await post_batch(client, publish_url, batch)
                lat_samples.append(lat)

        t0 = time.perf_counter()
        await asyncio.gather(*(worker(b) for b in batches))
        total_ms = (time.perf_counter() - t0) * 1000.0

        stop.set()
        await health_task

        # ambil stats akhir
        r = await client.get(stats_url, timeout=10.0)
        r.raise_for_status()
        stats = r.json()

    p_pub = percentiles(lat_samples, [50, 95, 99])
    p_h = percentiles(health_samples, [50, 95, 99])

    uniq_expected = int(args.total * (1 - args.dup_ratio))
    dup_expected = args.total - uniq_expected

    print("=== Perf Summary ===")
    print(f"run_id: {run_id}")
    print(f"batches={len(batches)} batch_size={args.batch_size} concurrency={args.concurrency}")
    print(f"total_events={args.total} dup_ratio={args.dup_ratio:.2f}")
    print(f"elapsed_ms={total_ms:.1f}")
    print(f"publish_ms_p50={p_pub[50]:.1f} p95={p_pub[95]:.1f} p99={p_pub[99]:.1f}")
    print(f"health_ms_p50={p_h[50]:.1f} p95={p_h[95]:.1f} p99={p_h[99]:.1f}")
    print("=== Aggregator Stats ===")
    print(json.dumps(stats, indent=2))
    print("=== Assertions ===")
    ok_unique = stats.get("unique_processed", -1) >= uniq_expected
    ok_dup = stats.get("duplicate_dropped", -1) >= dup_expected
    ok_resp = (p_pub[95] is not None and p_pub[95] <= 200.0) and (p_h[95] is not None and p_h[95] <= 50.0)
    print(f"unique_processed >= {uniq_expected}: {ok_unique}")
    print(f"duplicate_dropped >= {dup_expected}: {ok_dup}")
    print(f"responsiveness OK (p95 thresholds): {ok_resp}")
    if not (ok_unique and ok_dup and ok_resp):
        raise SystemExit(1)

if __name__ == "__main__":
    asyncio.run(main())