"""Rapid consecutive messages are answered once, as a batch."""

from __future__ import annotations

import asyncio

from app.companion.coordinator import ChatCoordinator


async def test_messages_within_debounce_are_batched():
    batches: list[list[int]] = []

    async def process(chat_id: int, ids: list[int]) -> None:
        batches.append(ids)

    coordinator = ChatCoordinator(process, debounce=0.05, max_wait=1.0)
    coordinator.submit(1, 10)
    await asyncio.sleep(0.01)
    coordinator.submit(1, 11)
    coordinator.submit(1, 12)
    await asyncio.sleep(0.15)
    assert batches == [[10, 11, 12]]

    coordinator.submit(1, 13)
    await asyncio.sleep(0.15)
    assert batches == [[10, 11, 12], [13]]
    await coordinator.shutdown()


async def test_messages_during_processing_can_be_merged():
    seen: list[list[int]] = []
    coordinator: ChatCoordinator

    async def process(chat_id: int, ids: list[int]) -> None:
        await asyncio.sleep(0.05)  # "typing"
        ids = ids + coordinator.take_pending(chat_id)
        seen.append(ids)

    coordinator = ChatCoordinator(process, debounce=0.01, max_wait=1.0)
    coordinator.submit(1, 1)
    await asyncio.sleep(0.03)
    coordinator.submit(1, 2)  # arrives while the first batch is being processed
    await asyncio.sleep(0.2)
    assert seen == [[1, 2]]
    await coordinator.shutdown()
