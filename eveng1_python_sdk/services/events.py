"""
Event handling service for G1 glasses
Provides high-level event orchestration and subscription management
"""
import asyncio
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Any
from time import time

from utils.constants import StateEvent, EventCategories, COMMANDS
from utils.logger import user_guidance

@dataclass
class EventContext:
    """Context information for events"""
    side: Optional[str]  # 'left' or 'right'
    timestamp: float
    raw_data: Optional[bytes] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

class EventService:
    """Handles event processing and distribution"""
    def __init__(self, connector):
        self.connector = connector
        self.logger = connector.logger
        self._shutting_down = False  # Add shutdown flag
        
        # Initialize handlers
        self._state_handlers = {
            'physical': {},  # For PHYSICAL_STATES
            'battery': {},   # For BATTERY_STATES
            'device': {},    # For DEVICE_STATES
            'interaction': {} # For INTERACTIONS
        }
        self._connection_handlers = {}  # Connection state handlers
        self._raw_handlers = {}        # Raw event handlers
        
    def subscribe_connection(self, callback):
        """Subscribe to connection state changes"""
        if callback not in self._connection_handlers:
            self._connection_handlers[callback] = True
            self.logger.debug(f"Added connection handler: {callback}")
            
    def subscribe_raw(self, event_type: int, callback):
        """Subscribe to raw event data for specific event type"""
        if event_type not in self._raw_handlers:
            self._raw_handlers[event_type] = {}
        if callback not in self._raw_handlers[event_type]:
            self._raw_handlers[event_type][callback] = True
            self.logger.debug(f"Added raw event handler for type 0x{event_type:02x}: {callback}")
        
    def unsubscribe_raw(self, event_type: int, callback):
        """Unsubscribe from raw event data for specific event type"""
        if event_type in self._raw_handlers and callback in self._raw_handlers[event_type]:
            del self._raw_handlers[event_type][callback]
            self.logger.debug(f"Removed raw event handler for type 0x{event_type:02x}: {callback}")
            # Clean up empty event type dict
            if not self._raw_handlers[event_type]:
                del self._raw_handlers[event_type]
        
    async def process_notification(self, side: str, data: bytes):
        """Process and distribute notifications"""
        if self._shutting_down or not data:  # Check shutdown flag
            return
            
        event_type = data[0]
        context = EventContext(side=side, timestamp=time(), raw_data=data)
        
        # Handle state events (0xF5)
        if event_type == 0xF5:
            state_code = data[1]
            # First update state manager
            await self.connector.state_manager.process_raw_state(data, side)
            
            # Then distribute to appropriate handlers based on state type
            if state_code in StateEvent.PHYSICAL_STATES:
                await self._dispatch_event(state_code, context, self._state_handlers['physical'])
            elif state_code in StateEvent.BATTERY_STATES:
                await self._dispatch_event(state_code, context, self._state_handlers['battery'])
            elif state_code in StateEvent.DEVICE_STATES:
                await self._dispatch_event(state_code, context, self._state_handlers['device'])
            elif state_code in StateEvent.INTERACTIONS:
                await self._dispatch_event(state_code, context, self._state_handlers['interaction'])
        
        # Handle heartbeat responses (0x25)
        elif event_type == COMMANDS.HEARTBEAT:
            await self.connector.state_manager.process_raw_state(data, side)
            if event_type in self._raw_handlers:
                await self._dispatch_event(event_type, context, self._raw_handlers[event_type])
        else:
            # Forward to raw handlers
            if event_type in self._raw_handlers:
                await self._dispatch_event(event_type, context, self._raw_handlers[event_type])

    async def _dispatch_event(self, event_type: int, context: EventContext, handlers: dict):
        """Dispatch event to registered handlers"""
        try:
            # For raw handlers, handlers is the dict of handlers for this event type
            if isinstance(handlers, dict) and handlers:  # If handlers is a non-empty dict
                for handler in handlers.keys():
                    try:
                        await handler(context.raw_data, context.side)
                    except Exception as e:
                        self.logger.error(f"Error in event handler: {e}")
        except Exception as e:
            self.logger.error(f"Error dispatching event: {e}")

    def shutdown(self):
        """Initiate graceful shutdown"""
        self._shutting_down = True
        # Clear all handlers to prevent further callbacks
        self._state_handlers = {key: {} for key in self._state_handlers}
        self._connection_handlers = {}
        self._raw_handlers = {}