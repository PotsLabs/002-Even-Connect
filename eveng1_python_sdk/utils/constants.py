"""Constants for G1 glasses SDK"""
from enum import Enum, IntEnum
from typing import Dict, Tuple

class ConnectionState(str, Enum):
    """Connection states for G1 glasses"""
    DISCONNECTED = "Disconnected"
    CONNECTING = "Connecting..."
    CONNECTED = "Connected"
    SCANNING = "Scanning..."
    PAIRING = "Pairing..."
    PAIRING_FAILED = "Pairing Failed"

class StateColors:
    """Color definitions for different states"""
    SUCCESS = "green"
    WARNING = "yellow"
    ERROR = "red"
    INFO = "blue"
    NEUTRAL = "grey70"
    HIGHLIGHT = "cyan"
    BRIGHT = "bright_blue"

class StateEvent:
    """State events (0xF5) and their subcategories"""
    
    # Physical States with their display properties
    PHYSICAL_STATES: Dict[int, Tuple[str, str, str]] = {
        0x06: ("WEARING", "Wearing", StateColors.SUCCESS),
        0x07: ("TRANSITIONING", "Transitioning", StateColors.WARNING),
        0x08: ("CRADLE", "Cradle open", StateColors.INFO),
        0x09: ("CRADLE_FULL", "Charged in cradle", StateColors.SUCCESS),
        0x0b: ("CRADLE_CLOSED", "Cradle closed", StateColors.INFO),
    }
    
    # Device States
    DEVICE_STATES: Dict[int, Tuple[str, str]] = {
        0x0a: ("DEVICE_UNKNOWN_0a", "Device unknown 0a"), # this one started appearing after the firmware update on 2025-01-02 (left and right)
        0x11: ("CONNECTED", "Successfully connected"), # assumed because its usualy at the start of the connection
        0x12: ("DEVICE_UNKNOWN_12", "Device unknown 12"), # seen, unclear purpose
        0x14: ("DEVICE_UNKNOWN_15", "Device unknown 14"), # seen, unclear purpose
        0x15: ("DEVICE_UNKNOWN_16", "Device unknown 15") # seen, unclear purpose
    }

    # Battery States - (code, system_name, display_label)
    BATTERY_STATES: Dict[int, Tuple[str, str]] = {
        0x09: ("GLASSES_CHARGED", "Glasses fully charged"),
        0x0e: ("CABLE_CHARGING", "Cradle charging cable state changed"),
        0x0f: ("CRADLE_CHARGED", "Cradle fully charged"),
    }
    
    # Interactions
    INTERACTIONS: Dict[int, Tuple[str, str]] = {
        0x00: ("DOUBLE_TAP", "Double tap"),
        0x01: ("SINGLE_TAP", "Single tap"),
        0x17: ("LONG_PRESS", "Long press"),
        0x04: ("SILENT_MODE_ON", "Silent mode enabled"),
        0x05: ("SILENT_MODE_OFF", "Silent mode disabled"),
        0x02: ("OPEN_DASHBOARD_START", "Open dashboard start"),
        0x03: ("CLOSE_DASHBOARD_START", "Close dashboard start"),
        0x1E: ("OPEN_DASHBOARD_CONFIRM", "Open dashboard confirmed"),
        0x1F: ("CLOSE_DASHBOARD_CONFIRM", "Close dashboard confirmed")
    }

    @classmethod
    def get_physical_state(cls, code) -> Tuple[str, str, str]:
        """Get physical state name, label and color"""
        try:
            if isinstance(code, str):
                if code.startswith('f5'):
                    code = int(code[2:], 16)
                else:
                    code = int(code, 16)
                    
            if code in cls.PHYSICAL_STATES:
                return cls.PHYSICAL_STATES[code]
                
            return "UNKNOWN", f"Unknown (0x{code:02x})", StateColors.ERROR
            
        except (ValueError, TypeError):
            return "UNKNOWN", "Invalid State Code", StateColors.ERROR

    @classmethod
    def get_device_state(cls, code: int) -> Tuple[str, str]:
        """Get device state name and label"""
        return cls.DEVICE_STATES.get(code, ("UNKNOWN", f"Unknown (0x{code:02X})"))

    @classmethod
    def get_interaction(cls, code: int) -> Tuple[str, str]:
        """Get interaction name and label"""
        return cls.INTERACTIONS.get(code, ("UNKNOWN", f"Unknown (0x{code:02X})"))

class UUIDS:
    """Bluetooth UUIDs for G1 glasses"""
    UART_SERVICE = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
    UART_TX = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
    UART_RX = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

class COMMANDS:
    """Command codes for G1 glasses"""
    HEARTBEAT = 0x25
    SILENT_MODE_ON = 0x04 # 3 taps
    SILENT_MODE_OFF = 0x05 # 3 taps
    AI_ENABLE = 0x17 #long press left
    HEARTBEAT_CMD = bytes([0x25, 0x06, 0x00, 0x01, 0x04, 0x01])
    BRIGHTNESS = 0x01

class StateDisplay:
    """Display information derived from StateEvent definitions"""
    @staticmethod
    def get_physical_states() -> Dict[str, Tuple[str, str]]:
        """Generate physical states display dictionary"""
        states = {
            name: (color, label) 
            for _, (name, label, color) in StateEvent.PHYSICAL_STATES.items()
        }
        # Add unknown state
        states["UNKNOWN"] = (StateColors.ERROR, "Unknown")
        return states
    
    # Access as a class variable
    PHYSICAL_STATES = get_physical_states()

    CONNECTION_STATES = {
        ConnectionState.CONNECTED: StateColors.SUCCESS,
        ConnectionState.DISCONNECTED: StateColors.ERROR,
        ConnectionState.CONNECTING: StateColors.WARNING,
        ConnectionState.SCANNING: StateColors.INFO,
        ConnectionState.PAIRING: StateColors.WARNING,
        ConnectionState.PAIRING_FAILED: StateColors.ERROR
    }

class EventCategories:
    """Event categories for G1 glasses"""
    STATE_CHANGE = 0xf5
    DASHBOARD = 0x22
    HEARTBEAT = 0x25
    RESPONSE = 0x03
    ERROR = 0x04


