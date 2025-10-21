# src/main.py
import asyncio
import datetime
import sqlite3
import logging
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends
from src.models import Event, AggregatorStats, ProcessedEvent

logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')

DB_PATH = "dedup_store.db"

class Aggregator:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.queue = asyncio.Queue()
        self.received_count = 0
        self.unique_count = 0
        self.duplicate_count = 0
        self.start_time = datetime.datetime.now()
        self._init_db()
        logging.info("Aggregator initialized with persistent SQLite store.")

    def _get_db_connection(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _init_db(self):
        conn = self._get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processed_events (
                event_id TEXT PRIMARY KEY,
                topic TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
        """)
        conn.commit()
        conn.close()

    async def add_event(self, event: Event):
        self.received_count += 1
        await self.queue.put(event)
        
    async def run_consumer(self):
        while True:
            event: Event = await self.queue.get()
            
            conn = self._get_db_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM processed_events WHERE event_id = ?", (event.event_id,))
                
                if cursor.fetchone() is None:
                    self._mark_as_processed(conn, event)
                    self.unique_count += 1
                    logging.info(f"PROCESSED: {event.topic} | {event.event_id}")
                else:
                    self.duplicate_count += 1
                    logging.warning(f"DUPLICATE DROPPED: {event.topic} | {event.event_id}")
            
            except Exception as e:
                logging.error(f"Error processing event {event.event_id}: {e}")
            finally:
                conn.close()
                self.queue.task_done()

    def _mark_as_processed(self, conn: sqlite3.Connection, event: Event):
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO processed_events (event_id, topic, timestamp) VALUES (?, ?, ?)",
            (event.event_id, event.topic, event.timestamp.isoformat())
        )
        conn.commit()

    def get_processed_events(self, topic: Optional[str] = None) -> List[ProcessedEvent]:
        conn = self._get_db_connection()
        cursor = conn.cursor()
        query = "SELECT event_id, topic, timestamp FROM processed_events"
        params = []
        if topic:
            query += " WHERE topic = ?"
            params.append(topic)
        
        cursor.execute(query, params)
        events = [
            ProcessedEvent(
                event_id=row[0], 
                topic=row[1], 
                timestamp=datetime.datetime.fromisoformat(row[2])
            ) for row in cursor.fetchall()
        ]
        conn.close()
        return events

    def get_stats(self) -> AggregatorStats:
        uptime = int((datetime.datetime.now() - self.start_time).total_seconds())
        conn = self._get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT topic FROM processed_events")
        topics = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        return AggregatorStats(
            received=self.received_count,
            unique_processed=self.unique_count,
            duplicate_dropped=self.duplicate_count,
            topics=topics,
            uptime=uptime
        )

# --- FastAPI App Setup ---
app = FastAPI(title="Idempotent Log Aggregator")

def get_aggregator() -> Aggregator:
    global global_aggregator 
    if 'global_aggregator' not in globals():
        global_aggregator = Aggregator()
    return global_aggregator

global_aggregator = Aggregator()

@app.on_event("startup")
async def startup_event():
    global_aggregator = get_aggregator() 
    asyncio.create_task(global_aggregator.run_consumer())

@app.post("/publish", status_code=202)
async def publish_event(event: Event, agg: Aggregator = Depends(get_aggregator)):
    await agg.add_event(event)
    return {"status": "accepted", "event_id": event.event_id}

@app.get("/events", response_model=List[ProcessedEvent])
async def get_events(topic: Optional[str] = None, agg: Aggregator = Depends(get_aggregator)):
    return agg.get_processed_events(topic)

@app.get("/stats", response_model=AggregatorStats)
async def get_stats(agg: Aggregator = Depends(get_aggregator)):
    return agg.get_stats()