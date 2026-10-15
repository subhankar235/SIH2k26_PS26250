"""Asynchronous Kafka event consumer."""

import json
import logging
import asyncio
from typing import Optional, List
from aiokafka import AIOKafkaConsumer
from .equilibrium import EquilibriumEngine

logger = logging.getLogger("KafkaConsumer")

DEFAULT_TOPICS = [
    "logistics.aircraft.v1",
    "logistics.crew.v1",
    "logistics.weather.v1",
    "logistics.airport.v1",
    "logistics.cargo.v1",
    "air.threats.v1",
]


class IngestionEventConsumer:
    """Consumes domain events from Kafka and feeds them to the equilibrium engine."""

    def __init__(
        self,
        bootstrap_servers: str = "localhost:29092",
        topics: Optional[List[str]] = None,
        group_id: str = "agent-engine-group",
        engine: Optional[EquilibriumEngine] = None,
    ):
        self.bootstrap_servers = bootstrap_servers
        self.topics = topics or DEFAULT_TOPICS
        self.group_id = group_id
        self.engine = engine or EquilibriumEngine()
        self.consumer: Optional[AIOKafkaConsumer] = None
        self._running = False

    async def start(self) -> None:
        """Start Kafka consumer loop."""
        self.consumer = AIOKafkaConsumer(
            *self.topics,
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.group_id,
            auto_offset_reset="latest",
            enable_auto_commit=True,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        )
        await self.consumer.start()
        self._running = True
        logger.info(f"Subscribed to Kafka topics: {self.topics}")

    async def consume_loop(self) -> None:
        """Continuously poll and process events."""
        if not self.consumer:
            raise RuntimeError("Consumer not started")

        try:
            async for msg in self.consumer:
                if not self._running:
                    break
                event = msg.value
                logger.info(f"Received event: {event.get('type')} for {event.get('entityId')}")
                # Feed into equilibrium engine
                await self.engine.ingest_event(event)
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop consumer."""
        self._running = False
        if self.consumer:
            await self.consumer.stop()

