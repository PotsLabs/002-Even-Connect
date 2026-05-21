"""State management service for G1 glasses"""
from typing import Optional, List, Callable
import asyncio
import time
from utils.constants import ConnectionState, StateEvent, EventCategories, COMMANDS, StateColors

class StateManager:
    """Manages state for G1 glasses"""
    
    def __init__(self, connector):
        self.connector = connector
        self.logger = connector.logger
        self._connection_state = ConnectionState.DISCONNECTED
        self._physical_state = None
        self._last_interaction = None
        self._raw_state_callbacks: List[Callable] = []
        self._state_callbacks: List[Callable] = []
        
        # Restore additional state tracking
        self._battery_state = None
        self._last_interaction_side = None
        self._last_interaction_time = None
        self._shutting_down = False
        self._last_heartbeat = None
        self._ai_enabled = False
        self._unrecognized_states = set()
        
        # Dashboard-specific attributes
        self._dashboard_mode = False
        self.silent_mode = False
        self._last_device_state = None
        self._last_device_state_time = None
        self._last_device_state_label = "Unknown"
        self.battery_state = "Unknown"
        
        self._last_known_state = None
        self._last_update = None
        
        # Add error tracking
        self._error_counts = {"left": 0, "right": 0}
        self._last_error_time = {"left": None, "right": None}
        
    def add_raw_state_callback(self, callback: Callable):
        """Add callback for raw state updates"""
        if callback not in self._raw_state_callbacks:
            self._raw_state_callbacks.append(callback)
            
    def remove_raw_state_callback(self, callback: Callable):
        """Remove raw state callback"""
        if callback in self._raw_state_callbacks:
            self._raw_state_callbacks.remove(callback)
            
    def add_state_callback(self, callback: Callable):
        """Add callback for processed state updates"""
        if callback not in self._state_callbacks:
            self._state_callbacks.append(callback)
            
    def remove_state_callback(self, callback: Callable):
        """Remove state callback"""
        if callback in self._state_callbacks:
            self._state_callbacks.remove(callback)
    
    @property
    def connection_state(self) -> ConnectionState:
        """Get current connection state"""
        return self._connection_state
        
    @connection_state.setter
    def connection_state(self, state: ConnectionState):
        """Set connection state"""
        if state != self._connection_state:
            self._connection_state = state
            self.logger.info(f"Connection state changed to: {state}")
            self._notify_state_callbacks()
            
    def set_connection_state(self, state: ConnectionState):
        """Set connection state (method form)"""
        self.connection_state = state
        
    @property
    def physical_state(self) -> str:
        """Get current physical state"""
        if self._physical_state is None:
            return "UNKNOWN"
        # Get all three values but only return the name
        name, _, _ = StateEvent.PHYSICAL_STATES.get(self._physical_state, ("UNKNOWN", "Unknown", StateColors.ERROR))
        return name
        
    @property
    def battery_state(self) -> str:
        """Get current battery state"""
        if self._battery_state is None:
            return "UNKNOWN"
        name, label = StateEvent.BATTERY_STATES.get(self._battery_state, ("UNKNOWN", "Unknown"))
        return label
        
    @property
    def device_state(self) -> str:
        """Get current device state"""
        if self._last_device_state is None:
            return "UNKNOWN"
        name, label = StateEvent.DEVICE_STATES.get(self._last_device_state, ("UNKNOWN", "Unknown"))
        return label
        
    @property
    def last_interaction(self) -> str:
        """Get last interaction"""
        if self._last_interaction:
            if self._last_interaction_side:
                return f"{self._last_interaction} ({self._last_interaction_side})"
            return self._last_interaction
        return "None"
        
    @property
    def last_heartbeat(self) -> float:
        """Get last heartbeat timestamp"""
        return self._last_heartbeat if self._last_heartbeat else None

    def update_physical_state(self, state: int):
        """Update physical state"""
        if state != self._physical_state:
            self._physical_state = state
            name, label = StateEvent.get_physical_state(state)
            self.logger.info(f"Physical state changed to: {label}")
            self._notify_state_callbacks()
            
    def update_interaction(self, interaction: str):
        """Update last interaction"""
        self._last_interaction = interaction
        self.logger.debug(f"Last interaction updated: {interaction}")
        self._notify_state_callbacks()
        
    def _notify_state_callbacks(self):
        """Notify all state callbacks"""
        for callback in self._state_callbacks:
            try:
                callback()
            except Exception as e:
                self.logger.error(f"Error in state callback: {e}")
                
    async def process_raw_state(self, data: bytes, side: str):
        """Process raw state data from glasses"""
        try:
            hex_data = data.hex()
            self.logger.debug(f"Processing raw state from {side}: {hex_data}")
            
            # Handle state change events (0xF5)
            if data[0] == 0xF5:
                state_code = data[1]
                
                # Get state label based on type
                label = "Unknown"
                if state_code in StateEvent.PHYSICAL_STATES:
                    _, label, _ = StateEvent.PHYSICAL_STATES[state_code]
                    self._physical_state = state_code
                    self.logger.debug(f"Updated physical state to: {label} ({hex_data})")
                elif state_code in StateEvent.BATTERY_STATES:
                    _, label = StateEvent.BATTERY_STATES[state_code]
                    self._battery_state = state_code
                    self.logger.debug(f"Updated battery state to: {label} ({hex_data})")
                elif state_code in StateEvent.DEVICE_STATES:
                    _, label = StateEvent.DEVICE_STATES[state_code]
                    self._last_device_state = state_code
                    self.logger.debug(f"Updated device state to: {label} ({hex_data})")
                elif state_code in StateEvent.INTERACTIONS:
                    _, label = StateEvent.INTERACTIONS[state_code]
                    self._last_interaction = label
                    self.logger.debug(f"Updated interaction to: {label} ({side})")
                    
                # Notify raw state callbacks with the processed state code and label
                for callback in self._raw_state_callbacks:
                    try:
                        await callback(state_code, side, label)
                    except Exception as e:
                        self.logger.error(f"Error in raw state callback: {e}")
                        
                self._notify_state_callbacks()
                
            # Handle heartbeat responses (0x25)
            elif data[0] == COMMANDS.HEARTBEAT:
                self._last_heartbeat = time.time()
                self.logger.debug(f"Updated heartbeat from {side}")
                self._notify_state_callbacks()
                
            # Handle silent mode changes
            elif data[0] == COMMANDS.SILENT_MODE_ON:
                self.silent_mode = True
                self.logger.debug("Silent mode enabled")
                self._notify_state_callbacks()  # Notify callbacks for UI update
            elif data[0] == COMMANDS.SILENT_MODE_OFF:
                self.silent_mode = False
                self.logger.debug("Silent mode disabled")
                self._notify_state_callbacks()  # Notify callbacks for UI update
                
        except Exception as e:
            self.logger.error(f"Error processing state: {e}")
        
    def set_dashboard_mode(self, enabled: bool):
        """Enable or disable dashboard mode"""
        self._dashboard_mode = enabled
        if enabled:
            self.logger.debug("Dashboard mode enabled")
        else:
            self.logger.debug("Dashboard mode disabled")
            
    def shutdown(self):
        """Clean shutdown of state manager"""
        self._shutting_down = True
        self._connection_state = ConnectionState.DISCONNECTED
        self._dashboard_mode = False
        self._state_callbacks.clear()
        
    @property
    def battery_state(self):
        """Get current battery state"""
        return self._battery_state
        
    @battery_state.setter
    def battery_state(self, value):
        """Set battery state"""
        self._battery_state = value

    async def handle_state_change(self, new_state: int, side: str = None):
        """Handle state change from glasses"""
        if self._shutting_down:
            return
            
        try:
            # Update appropriate state based on category
            if new_state in StateEvent.BATTERY_STATES:
                self._battery_state = new_state
                
            if new_state in StateEvent.INTERACTIONS:
                self._last_interaction = new_state
                self._last_interaction_side = side
                self._last_interaction_time = time.time()
                
            # Track unrecognized states
            if not any(new_state in category for category in [
                StateEvent.PHYSICAL_STATES,
                StateEvent.DEVICE_STATES,
                StateEvent.BATTERY_STATES,
                StateEvent.INTERACTIONS
            ]):
                if new_state not in self._unrecognized_states:
                    self._unrecognized_states.add(new_state)
                    self.logger.debug(f"Unrecognized state: 0x{new_state:02x} ({new_state}) from {side} glass")
                    
            await self._notify_state_callbacks()
            
        except Exception as e:
            self.logger.error(f"Error handling state change: {e}")
        
    def increment_error_count(self, side: str):
        """Increment error count for specified side"""
        if side in self._error_counts:
            self._error_counts[side] += 1
            self._last_error_time[side] = time.time()
            self.logger.debug(f"Error count for {side}: {self._error_counts[side]}")
            self._notify_state_callbacks()
            
    @property
    def error_counts(self):
        """Get current error counts"""
        return self._error_counts
        