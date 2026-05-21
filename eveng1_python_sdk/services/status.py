"""Status display service for G1 glasses"""
import asyncio
import time
from rich.table import Table
from rich.live import Live
from rich.text import Text

from utils.constants import StateEvent, EventCategories

class StatusManager:
    """Manages status display and dashboard"""
    
    def __init__(self, connector):
        self.connector = connector
        self.logger = connector.logger
        self._live = None
        self._running = False
        
    def generate_table(self) -> Table:
        """Generate status table for display"""
        table = Table(title="G1 Glasses Status")
        
        # Add columns first for consistent layout
        table.add_column("Device", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Signal", style="yellow")
        table.add_column("Errors", style="red")

        # Connection Status Section
        self._add_connection_status(table)
        
        # Device State Section
        self._add_device_states(table)
        
        # Event Status Section
        self._add_event_status(table)
        
        # System Status Section
        self._add_system_status(table)
        
        return table

    def _add_connection_status(self, table: Table):
        """Add connection status information"""
        # Left glass status
        left_rssi = self.connector._connection_quality['left']['rssi']
        left_errors = self.connector._connection_quality['left']['errors']
        table.add_row(
            f"Left Glass ({self.connector.config.left_name or 'Not Found'})",
            "Connected" if self.connector.left_client and self.connector.left_client.is_connected else "Disconnected",
            f"{left_rssi}dBm" if left_rssi else "N/A",
            str(left_errors)
        )
        
        # Right glass status
        right_rssi = self.connector._connection_quality['right']['rssi']
        right_errors = self.connector._connection_quality['right']['errors']
        table.add_row(
            f"Right Glass ({self.connector.config.right_name or 'Not Found'})",
            "Connected" if self.connector.right_client and self.connector.right_client.is_connected else "Disconnected",
            f"{right_rssi}dBm" if right_rssi else "N/A",
            str(right_errors)
        )

    def _add_device_states(self, table: Table):
        """Add device state information"""
        # Physical State - use both state manager and event service
        physical_state = self.connector.state_manager.physical_state
        event_state = self._get_last_event_of_type(StateEvent.PHYSICAL_STATES)
        table.add_row(
            "Physical State",
            f"{physical_state} ({event_state})" if event_state else physical_state,
            "",
            ""
        )

        # Device State
        device_state = self._get_last_event_of_type(StateEvent.DEVICE_STATES)
        if device_state:
            table.add_row("Device State", device_state, "", "")
            
        # Battery State - Added
        battery_state = self.connector.state_manager.battery_state
        if battery_state:
            table.add_row("Battery State", battery_state, "", "")
            
        # AI Status
        table.add_row(
            "AI Status",
            "Enabled" if self.connector.event_service._ai_enabled else "Disabled",
            "",
            ""
        )
        
        # Silent Mode
        table.add_row(
            "Silent Mode",
            "On" if self.connector.event_service._silent_mode else "Off",
            "",
            ""
        )

    def _add_event_status(self, table: Table):
        """Add recent event information"""
        # Last Interaction - use both state manager and event service
        interaction = self.connector.state_manager.last_interaction
        if interaction and interaction != "None":
            table.add_row(
                "Last Interaction",
                interaction,
                "",
                ""
            )
        
        # Last Heartbeat
        last_heartbeat = self.connector.event_service.last_heartbeat
        if last_heartbeat:
            time_ago = time.time() - last_heartbeat
            table.add_row(
                "Last Heartbeat",
                f"{time_ago:.1f}s ago",
                "",
                ""
            )

    def _add_system_status(self, table: Table):
        """Add system status information"""
        table.add_section()
        
        # Connection State
        table.add_row(
            "Connection",
            self.connector.state_manager.connection_state,
            "",
            ""
        )
        
        # Add any error counts or system messages
        error_count = sum(side['errors'] for side in self.connector._connection_quality.values())
        if error_count > 0:
            table.add_row(
                "Total Errors",
                str(error_count),
                "",
                ""
            )

    def _get_last_event_of_type(self, event_dict: dict) -> str:
        """Helper to get last event of a specific type"""
        recent_events = self.connector.event_service.get_recent_events()
        for event_code, context in reversed(recent_events):
            if event_code in event_dict:
                return event_dict[event_code][1]
        return "Unknown"

    async def start(self) -> None:
        """Start live status display"""
        if self._running:
            return
            
        self._running = True
        self._live = Live(
            self.generate_table(),
            refresh_per_second=1,
            console=self.connector.console
        )
        self._live.start()
        
        while self._running:
            self._live.update(self.generate_table())
            await asyncio.sleep(1)
            
    async def stop(self) -> None:
        """Stop live status display"""
        self._running = False
        if self._live:
            self._live.stop()
            
    async def update(self) -> None:
        """Update status display"""
        if self._live:
            try:
                self._live.update(self.generate_table())
            except Exception as e:
                self.logger.error(f"Error updating status display: {e}") 