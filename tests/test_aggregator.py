import pytest
import asyncio
import uuid
import datetime
import os
import pytest_asyncio
import src.main

from src.main import app, Aggregator
from src.models import Event, EventPayload
from httpx import AsyncClient, ASGITransport

# Fixtures and Setup 

TEST_DB_PATH = "test_dedup_store.db"

@pytest.fixture(scope="session", autouse=True)
def cleanup_db():
    yield
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)

@pytest_asyncio.fixture
async def test_aggregator():
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
        
    agg = Aggregator(db_path=TEST_DB_PATH)
    
    agg.received_count = 0
    agg.unique_count = 0
    agg.duplicate_count = 0
    agg.start_time = datetime.datetime.now()
    
    await asyncio.sleep(1.0) 

    consumer_task = asyncio.create_task(agg.run_consumer())
    
    yield agg
    
    consumer_task.cancel()
    try:
        await consumer_task 
    except asyncio.CancelledError:
        pass
    except Exception:
        pass 
        
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)


@pytest_asyncio.fixture
async def test_client(test_aggregator):
    
    original_global_agg = src.main.global_aggregator
    src.main.global_aggregator = test_aggregator 

    app.dependency_overrides[src.main.get_aggregator] = lambda: test_aggregator
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
        
    app.dependency_overrides = {} 
    src.main.global_aggregator = original_global_agg

def create_mock_event(event_id=None, topic="test.log", source="service-A"):
    return Event(
        topic=topic,
        event_id=event_id if event_id else str(uuid.uuid4()),
        timestamp=datetime.datetime.now(datetime.timezone.utc),
        source=source,
        payload=EventPayload(content="Test log message")
    )

# Unit Tests

@pytest.mark.asyncio
async def test_t1_deduplication_validity(test_client, test_aggregator):
    """Test 1: Kirim duplikat, pastikan hanya sekali diproses (Idempotency)."""
    
    unique_id = str(uuid.uuid4())
    event_1 = create_mock_event(event_id=unique_id)
    event_2_duplicate = create_mock_event(event_id=unique_id)

    await test_client.post("/publish", json=event_1.model_dump(mode='json'))
    await test_client.post("/publish", json=event_2_duplicate.model_dump(mode='json'))

    await test_aggregator.queue.join()

    events_response = await test_client.get("/events")
    events = events_response.json()
    assert len(events) == 1
    assert events[0]['event_id'] == unique_id
    
    stats_response = await test_client.get("/stats")
    stats = stats_response.json()
    assert stats['received'] == 2
    assert stats['unique_processed'] == 1
    assert stats['duplicate_dropped'] == 1

@pytest.mark.asyncio
async def test_t2_persistence_after_restart(test_aggregator):
    """Test 2: Persistensi dedup store - setelah restart (simulasi), dedup tetap efektif."""
    
    unique_id = str(uuid.uuid4())
    event_a = create_mock_event(event_id=unique_id)

    agg = test_aggregator
    await agg.add_event(event_a) 
    await asyncio.sleep(0.5) 
    assert agg.unique_count == 1
    
    restarted_aggregator = Aggregator(db_path=TEST_DB_PATH)
    consumer_task = asyncio.create_task(restarted_aggregator.run_consumer())
    await asyncio.sleep(0.1) 
    
    event_a_duplicate = create_mock_event(event_id=unique_id)
    await restarted_aggregator.add_event(event_a_duplicate)
    await restarted_aggregator.queue.join() 
    
    stats = restarted_aggregator.get_stats()
    assert stats.received == 1
    assert stats.unique_processed == 0
    assert stats.duplicate_dropped == 1
    
    consumer_task.cancel()
    try:
        await consumer_task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_t3_event_schema_validation(test_client):
    """Test 3: Validasi skema event (pastikan Pydantic menolak event tanpa event_id)."""
    invalid_data = {
        "topic": "test.log",
        "timestamp": datetime.datetime.now().isoformat(),
        "source": "service-A",
        "payload": {"content": "Test"}
    }
    
    response = await test_client.post("/publish", json=invalid_data)
    
    assert response.status_code == 422
    assert "event_id" in response.json()['detail'][0]['loc']

@pytest.mark.asyncio
async def test_t4_get_stats_consistency(test_client, test_aggregator):
    """Test 4: Konsistensi GET /stats dengan data yang dimasukkan."""
    
    event_1 = create_mock_event(topic="topic.a")
    event_2 = create_mock_event(topic="topic.b")
    
    await test_client.post("/publish", json=event_1.model_dump(mode='json'))
    await test_client.post("/publish", json=event_2.model_dump(mode='json'))
    await test_aggregator.queue.join()
    
    stats_response = await test_client.get("/stats")
    stats = stats_response.json()
    
    assert stats['received'] == 2
    assert stats['unique_processed'] == 2
    assert stats['duplicate_dropped'] == 0
    assert set(stats['topics']) == {"topic.a", "topic.b"}
    assert stats['uptime'] > 0

@pytest.mark.asyncio
async def test_t5_get_events_with_topic_filter(test_client, test_aggregator):
    """Test 5: Konsistensi GET /events dengan filter topic."""
    
    event_a1 = create_mock_event(topic="finance.tx")
    event_b1 = create_mock_event(topic="finance.audit")
    event_a2_dup = create_mock_event(event_id=event_a1.event_id, topic="finance.tx")
    
    await test_client.post("/publish", json=event_a1.model_dump(mode='json'))
    await test_client.post("/publish", json=event_b1.model_dump(mode='json'))
    await test_client.post("/publish", json=event_a2_dup.model_dump(mode='json'))
    await test_aggregator.queue.join()
    
    tx_events_response = await test_client.get("/events?topic=finance.tx")
    tx_events = tx_events_response.json()
    assert len(tx_events) == 1
    assert tx_events[0]['event_id'] == event_a1.event_id
    
    audit_events_response = await test_client.get("/events?topic=finance.audit")
    audit_events = audit_events_response.json()
    assert len(audit_events) == 1
    assert audit_events[0]['event_id'] == event_b1.event_id

@pytest.mark.asyncio
async def test_t6_stress_small_batch(test_client, test_aggregator):
    """Test 6: Stress test kecil - memproses batch event."""
    NUM_EVENTS = 100
    events = [create_mock_event() for _ in range(NUM_EVENTS)]
    
    start_time = datetime.datetime.now()
    for event in events:
        await test_client.post("/publish", json=event.model_dump(mode='json'))
    
    await test_aggregator.queue.join() 
    
    end_time = datetime.datetime.now()
    duration = (end_time - start_time).total_seconds()

    stats_response = await test_client.get("/stats")
    stats = stats_response.json()
    
    assert stats['received'] == NUM_EVENTS
    assert stats['unique_processed'] == NUM_EVENTS
    assert stats['duplicate_dropped'] == 0
    
    assert duration < 5.0, f"Processing {NUM_EVENTS} events took too long: {duration:.2f}s"