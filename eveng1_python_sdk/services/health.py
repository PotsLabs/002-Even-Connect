"""Health monitoring service for G1 glasses"""
from typing import Callable, List
import asyncio
import time

class HealthMonitor:
    def __init__(self, connector):
        self.connector = connector
        self.logger = connector.logger
        self._heartbeat_handlers: List[Callable] = []
        self._last_heartbeat = None
        self._connection_quality = {
            'left': {'rssi': None, 'errors': 0, 'last_heartbeat': None},
            'right': {'rssi': None, 'errors': 0, 'last_heartbeat': None}
        }

    def subscribe_heartbeat(self, handler: Callable):
        """Subscribe to heartbeat events"""
        if handler not in self._heartbeat_handlers:
            self._heartbeat_handlers.append(handler)

    async def process_heartbeat(self, side: str, timestamp: float):
        """Process heartbeat from a specific side"""
        self._last_heartbeat = timestamp
        self._connection_quality[side]['last_heartbeat'] = timestamp
        
        await self._notify_handlers(timestamp)

    async def _notify_handlers(self, timestamp: float):
        """Notify all heartbeat handlers"""
        for handler in self._heartbeat_handlers:
            try:
                # Skip if handler is the connector's heartbeat handler to prevent recursion
                if handler == self.connector._handle_heartbeat:
                    continue
                    
                if asyncio.iscoroutinefunction(handler):
                    await handler(timestamp)
                else:
                    handler(timestamp)
            except Exception as e:
                self.logger.error(f"Error in heartbeat handler: {e}") 