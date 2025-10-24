import os
import shutil
import tempfile
import time
import random
import pytest
from fastapi.testclient import TestClient
from src.app import create_app

# helper event
def make_event(topic, eid, t="2025-10-24T00:00:00Z", src="test", payload=None):
    return {
        "topic": topic,
        "event_id": eid,
        "timestamp": t,
        "source": src,
        "payload": payload or {},
    }

# wait until processed_total advances or timeout
def wait_until_processed(client: TestClient, expected_total: int, timeout_s=2.0):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        s = client.get("/stats").json()
        if s["processed_total"] >= expected_total:
            return s
        time.sleep(0.02)
    return client.get("/stats").json()

@pytest.fixture
def temp_db_dir():
    d = tempfile.mkdtemp(prefix="deduptest_")
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)

@pytest.fixture
def make_client(temp_db_dir, request):
    # buat TestClient dengan DB path sementara
    def _mk(name="dedup.db"):
        db_path = os.path.join(temp_db_dir, name)
        app = create_app(dedup_db_path=db_path)
        ctx = TestClient(app)
        client = ctx.__enter__()  # start lifespan
        request.addfinalizer(lambda: ctx.__exit__(None, None, None))  # pastikan shutdown
        return client, db_path
    return _mk

def test_health(make_client):
    """Health check OK."""
    client, _ = make_client()
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

def test_schema_validation(make_client):
    """Validasi skema: timestamp harus ISO8601."""
    client, _ = make_client()
    bad = make_event("orders", "e1", t="not-a-timestamp")
    r = client.post("/publish", json={"events": [bad]})
    assert r.status_code == 422  # validator timestamp

def test_deduplication_single_topic(make_client):
    """Dedup: event duplikat hanya diproses sekali."""
    client, _ = make_client()
    ev1 = make_event("orders", "e1")
    ev2 = make_event("orders", "e2")
    r = client.post("/publish", json={"events": [ev1, ev2]})
    assert r.status_code == 202
    s = wait_until_processed(client, expected_total=2)

    # kirim duplikat e1
    r = client.post("/publish", json={"events": [ev1]})
    assert r.status_code == 202
    s = wait_until_processed(client, expected_total=3)

    assert s["received"] == 3
    assert s["unique_processed"] == 2
    assert s["duplicate_dropped"] == 1
    assert "orders" in s["topics"]

    events = client.get("/events", params={"topic": "orders"}).json()
    assert len(events) == 2  # e1 & e2; e1 sekali

def test_persistence_across_restart(make_client):
    """Persistensi dedup: restart tidak memproses ulang event sama."""
    # instance-1
    client1, db_path = make_client()
    ev = make_event("audit", "x1")
    r = client1.post("/publish", json={"events": [ev]})
    assert r.status_code == 202
    s1 = wait_until_processed(client1, expected_total=1)
    assert s1["unique_processed"] == 1

    # tutup instance-1 → simulasi restart
    client1.__exit__(None, None, None) if hasattr(client1, "__exit__") else None

    # instance-2 dengan DB sama
    app2 = create_app(dedup_db_path=db_path)
    ctx2 = TestClient(app2)
    client2 = ctx2.__enter__()
    try:
        r = client2.post("/publish", json={"events": [ev]})
        assert r.status_code == 202
        s2 = wait_until_processed(client2, expected_total=1)
        # unique_processed reset (in-memory), yang penting dupe terdeteksi
        assert s2["duplicate_dropped"] == 1
    finally:
        ctx2.__exit__(None, None, None)

def test_stats_events_consistency(make_client):
    """Stats/Events konsisten dengan data yang diproses."""
    client, _ = make_client()
    batch = [make_event("t", f"id{i}") for i in range(10)]
    r = client.post("/publish", json={"events": batch})
    assert r.status_code == 202
    s = wait_until_processed(client, expected_total=10)
    events = client.get("/events", params={"topic": "t"}).json()
    assert len(events) == 10
    assert s["unique_processed"] == 10
    assert s["received"] == 10

def test_stress_small_with_dupes(make_client):
    """Stress kecil: 1000 event, >=20% duplikat, waktu wajar."""
    client, _ = make_client()
    # 1000 total; 20% dupe
    N = 1000
    uniq = 800
    ids = [f"id{i}" for i in range(uniq)]
    events = []
    for i in range(N):
        if i < uniq:
            events.append(make_event("bench", ids[i]))
        else:
            events.append(make_event("bench", random.choice(ids)))  # dupe

    start = time.time()
    step = 200  # batch kirim
    sent = 0
    for i in range(0, N, step):
        batch = events[i:i+step]
        r = client.post("/publish", json={"events": batch})
        assert r.status_code == 202
        sent += len(batch)

    s = wait_until_processed(client, expected_total=sent, timeout_s=5.0)
    elapsed = time.time() - start

    assert s["received"] == N
    assert s["unique_processed"] == uniq
    assert s["duplicate_dropped"] == N - uniq
    assert elapsed < 5.0  # batas wajar