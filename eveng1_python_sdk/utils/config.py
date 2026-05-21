"""
Configuration management for G1 glasses
"""
import os
import json
from dataclasses import dataclass, asdict
from typing import Optional, Dict

@dataclass
class Config:
    """Configuration for G1 glasses SDK"""
    # Get the SDK root directory
    SDK_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    CONFIG_FILE = os.path.join(SDK_ROOT, "g1_config.json")
    
    # Logging configuration
    log_level: str = "INFO"
    log_file: str = os.path.join(SDK_ROOT, "g1_connector.log")
    console_log: bool = True
    reset_logs: bool = True
    
    # Connection configuration
    heartbeat_interval: float = 8.0  # Changed to float for more precise timing
    reconnect_attempts: int = 3
    reconnect_delay: float = 1.0  # seconds
    connection_timeout: float = 20.0  # Added connection timeout
    
    # Device information
    left_address: Optional[str] = None
    right_address: Optional[str] = None
    left_name: Optional[str] = None
    right_name: Optional[str] = None
    left_paired: bool = False
    right_paired: bool = False
    
    # Service information
    discovered_services: Dict[str, Dict] = None
    
    # Display settings (added)
    display_width: int = 488
    font_size: int = 21
    lines_per_screen: int = 5
    
    def save(self):
        """Save configuration to file with comments"""
        config_data = asdict(self)
        
        # Create SDK directory if it doesn't exist
        os.makedirs(os.path.dirname(self.CONFIG_FILE), exist_ok=True)
        
        comments = {
            "log_level": "Logging level (DEBUG/INFO/ERROR)",
            "log_file": "Log file path",
            "reset_logs": "Reset logs on startup",
            "console_log": "Enable console logging",
            "heartbeat_interval": "Seconds between heartbeat signals",
            "reconnect_attempts": "Number of reconnection attempts",
            "reconnect_delay": "Seconds between reconnection attempts",
            "left_address": "Left glass BLE address (clear to rescan)",
            "right_address": "Right glass BLE address (clear to rescan)",
            "left_name": "Left glass device name",
            "right_name": "Right glass device name",
            "discovered_services": "Discovered BLE services and characteristics"
        }
        
        commented_config = {
            "_comment": "G1 Glasses SDK Configuration",
            "_instructions": "Clear left_address and right_address to force new device scanning",
            "config": config_data
        }
        
        for key, comment in comments.items():
            commented_config[f"_{key}_comment"] = comment
        
        try:
            with open(self.CONFIG_FILE, 'w') as f:
                json.dump(commented_config, f, indent=2, sort_keys=False)
        except Exception as e:
            print(f"Error saving config: {e}")
    
    @classmethod
    def load(cls) -> 'Config':
        """Load configuration from file or create default"""
        try:
            with open(cls.CONFIG_FILE, 'r') as f:
                data = json.load(f)
                config_data = data.get("config", {})
                return cls(**config_data)
        except (FileNotFoundError, json.JSONDecodeError):
            # Create new config with defaults
            config = cls()
            config.save()
            return config
        except Exception as e:
            print(f"Unexpected error loading config: {e}")
            return cls() 