"""
Device management service for G1 glasses
if battery status is available, add that here too
"""

from utils.constants import COMMANDS, EventCategories

class DeviceManager:
    """Handles device-wide states and controls"""
    
    def __init__(self, connector):
        self.connector = connector
        self.logger = connector.logger
        self._silent_mode = False
        self._battery_level = {
            'left': None,
            'right': None
        }
    
    @property
    def silent_mode(self) -> bool:
        """Get current silent mode state"""
        return self._silent_mode
    
    async def set_silent_mode(self, enabled: bool) -> bool:
        """Set silent mode state (disables all functionality)"""
        try:
            if enabled == self._silent_mode:
                return True
                
            # Command structure for silent mode
            command = bytes([COMMANDS.DASHBOARD_OPEN, 0x01 if enabled else 0x00])
            
            result = await self.connector.command_manager.send_command(
                self.connector.right_client,
                command,
                expect_response=True
            )
            
            if result and result[1] == EventCategories.COMMAND_RESPONSE:
                self._silent_mode = enabled
                self.logger.info(f"Silent mode {'enabled' if enabled else 'disabled'}")
                await self.connector.update_status()
                return True
            
            self.logger.warning(f"Failed to set silent mode: unexpected response {result[1] if result else 'None'}")
            return False
            
        except Exception as e:
            self.logger.error(f"Error setting silent mode: {e}")
            return False

    async def set_brightness(self, level: int, auto: bool = False) -> bool:
        """Set the brightness level (0-41) for both glasses. If auto is True, enable auto brightness."""
        try:
            if not 0 <= level <= 41:
                self.logger.error(f"Brightness level {level} out of range (0-41)")
                return False
            auto_byte = 0x01 if auto else 0x00
            command = bytes([COMMANDS.BRIGHTNESS, level, auto_byte])
            success = True
            for client in [self.connector.left_client, self.connector.right_client]:
                if client and client.is_connected:
                    await self.connector.command_manager.send_command(
                        client,
                        command,
                        expect_response=False
                    )
            mode = 'AUTO' if auto else 'MANUAL'
            self.logger.info(f"Brightness set to {level} ({mode})")
            return success
        except Exception as e:
            self.logger.error(f"Error setting brightness: {e}")
            return False

    @property
    def battery_level(self) -> dict:
        """Get current battery levels"""
        return self._battery_level.copy()

    def update_battery_level(self, side: str, level: int):
        """Update battery level for specified side"""
        if side in self._battery_level:
            self._battery_level[side] = level
            self.logger.debug(f"Battery level updated for {side}: {level}%") 
