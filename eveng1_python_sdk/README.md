# G1 SDK

Python SDK for interacting with G1 Smart Glasses via Bluetooth LE. Provides a high-level interface for device communication, state management, and feature control.

## Installation

Requirements:
- Python 3.7+
- Bluetooth LE support

```bash
pip install -r requirements.txt
```


Required packages:
- bleak>=0.21.1: Bluetooth LE communication
- rich>=13.7.0: Enhanced console output
- asyncio>=3.4.3: Asynchronous I/O support

## Quick Start

Simple connection example:
```python
from connector import G1Connector
import asyncio

async def main():
    # Initialize connector
    glasses = G1Connector()
    
    # Connect to glasses (includes automatic retry logic)
    if await glasses.connect():
        print("Successfully connected to G1 glasses")
        # Your code here
    else:
        print("Failed to connect to glasses")

if __name__ == "__main__":
    asyncio.run(main())
```

## Features

### Bluetooth Management
- Robust BLE connection handling with configurable retry logic
- Automatic reconnection on disconnect
- Dual glass (left/right) connection support
- Connection state tracking and event notifications

### State Management
- Physical state monitoring (wearing, charging, cradle)
- Battery level tracking
- Device state updates
- Interaction event processing
- Dashboard mode support

### Event Handling
Supports various interaction types:
- Single/Double tap detection
- Long press actions
- Dashboard open/close events
- Silent mode toggles

### Display Control
Text display features:
- Multi-line text support
- Configurable font sizes
- Page-based text display
- Screen status tracking
- Brightness level adjustment
- Auto brightness on/off

Image display capabilities: (TODO)
- 1-bit, 576x136 pixel BMP format
- Packet-based transmission
- CRC verification
- Left/right glass synchronization

### Audio Features
Microphone control: (TODO)
- Right-side microphone activation
- LC3 format audio streaming
- 30-second maximum recording duration
- Real-time audio data access

### Even AI Integration
AI feature support: (TODO)
- Start/stop AI recording
- Manual/automatic modes
- Result display handling
- Network status monitoring

## Core Components

### Connector Module
Core connection and communication handling:
- `base.py`: Base class for all connectors
- `bluetooth.py`: BLE device management and connection handling
- `commands.py`: Command protocol implementation
- `pairing.py`: Device pairing and authentication

### Services Module
Individual feature implementations:
- `audio.py`: Microphone control and audio processing (TODO)
- `device.py`: Device interactions (TODO)
- `display.py`: Text and image display management (TODO)
- `events.py`: Listening and responding to G1 events
- `state.py`: State tracking and event management
- `status.py`: 
- `uart.py`: Low-level UART communication

### Utils Module
Supporting utilities:
- `config.py`: Configuration management
- `constants.py`: Protocol constants and enums
- `logger.py`: Logging configuration


## Flow

### First Time Setup
1. **Config Initialization**
   - `utils/config.py`: Creates default configuration if none exists
   - Default settings loaded from `g1_config.json`:
     ```json
     {
       "reconnect_attempts": 3,
       "reconnect_delay": 1.0,
       "connection_timeout": 20.0
     }
     ```

2. **Logging Setup**
   - `utils/logger.py`: Configures logging handlers
   - Creates log directory if not exists
   - Initializes both file and console logging
   - Log files stored in `./g1_connector.log`

3. **Bluetooth Discovery**
   - `connector/bluetooth.py`: `BLEManager.scan_for_glasses()`
   - Searches for devices matching G1 identifier
   - Returns list of discovered G1 glasses with addresses

4. **Pairing Process**
   - `connector/pairing.py`: Handles initial device pairing
   - Establishes secure connection with both left and right glasses
   - Validates device authenticity
   - Stores pairing information

5. **Connection Confirmation**
   - `connector/bluetooth.py`: `_connect_glass()`
   - Verifies successful connection to both glasses
   - Initializes UART service
   - Sets up notification handlers

6. **Device ID Storage**
   - Stores validated glass IDs in config file
   - Left glass address: `left_address`
   - Right glass address: `right_address`

### Subsequent Connections
1. **Direct Connection**
   - Reads stored glass IDs from config
   - `connector/bluetooth.py`: Attempts direct connection
   - Uses configured retry logic:
     ```python
     for attempt in range(self.connector.config.reconnect_attempts):
         # Connection attempt logic
     ```

2. **Connection Maintenance**
   - `connector/commands.py`: Sends periodic heartbeat
   - Default heartbeat command: `HEARTBEAT_CMD = bytes([0x25, 0x06, 0x00, 0x01, 0x04, 0x01])`
   - Monitors connection status
   - Automatic reconnection on disconnect

3. **Event Monitoring**
   - `services/state.py`: Manages state tracking
   - `services/uart.py`: Handles UART notifications
   - Event types defined in `utils/constants.py`:
     - Physical states (wearing, charging)
     - Device states (connected, operational)
     - Interactions (taps, gestures)
     - Battery status

## Examples

### Basic Usage

#### Simple Connect
`simple_connect.py`
Basic connection demonstration

```bash
python -m examples.simple_connect
```

#### Monitor State Changes
`interactions.py`
Monitor and log device interactions

```bash
python -m examples.interactions
```

#### Dashboard
`dashboard.py`
Monitor statuses and logs

```bash
python -m examples.dashboard
```

### Display Features

#### Text Display
`send_text.py`
Text display with multi-line support

```bash
python -m examples.send_text
```

#### PowerPoint Display (In progress)
`ppt_teleprompter.py`
Send speaker notes from an active PowerPoint presentation to the glasses

```bash
python -m examples.ppt_teleprompter
```

#### Image Display
`send_image.py`  (TODO)
Image transmission (1-bit, 576x136 BMP) 

```bash
python -m examples.send_image
```

### Advanced Features

#### Microphone
`microphone.py` (TODO)
Audio recording demonstration

```bash
python -m examples.microphone
```

#### Even AI
`even_ai.py` (TODO)
Even AI integration example 

```bash
python -m examples.even_ai
```

## Protocol Details

### Display Protocol
- Text display supports configurable font sizes and line counts
- Images must be 1-bit, 576x136 pixel BMP format
- Packet-based transmission with CRC verification

### Audio Protocol
- LC3 format audio streaming
- Right-side microphone activation
- 30-second maximum recording duration

### State Management
- Physical state tracking (wearing, charging, etc.)
- Battery level monitoring
- Interaction event processing

## Configuration

Default settings can be modified in `g1_config.json`:
- `device_name`: Customize the device name for pairing
- `device_address`: Manually set the device address
- `auto_reconnect`: Enable or disable automatic reconnection
- `log_level`: Set the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `log_file`: Specify a custom log file path
- `log_to_console`: Enable or disable logging to the console
- `log_to_file`: Enable or disable logging to a file


## Roadmap & Planned Improvements

### Immediate Priority
- [ ] clean up the console logs for a new connection, many duplicates and logs with markup
- [ ] Implement text sending functionality
- [ ] Add comprehensive examples for text display and interaction
- [ ] Document text positioning and formatting options

### High Priority (Developer Experience)
1. Connection Management
   - [ ] Implement Windows BLE connection recovery
     * Detect and reuse existing connections
     * Add configurable retry timing for connection attempts
     * Implement force-disconnect on SDK exit
     * Add connection state detection and logging

2. Pairing Improvements
   - [ ] Add robust pairing state detection and management
     * Detect proper pairing state vs. just connected state
     * Add automatic re-pairing when connection is incomplete avoiding the need to delete the config file
     * Add user guidance for connection troubleshooting

3. Documentation Improvements (add more detail to this readme doc)
   - [ ] Add inline examples in docstrings
   - [ ] add more detail/quickstarts/examples to this readme doc
   - [ ] Document error scenarios and solutions

4. Developer Tools
   - [ ] Create higher-level abstractions for common patterns
   - [ ] Add more example applications
   - [ ] Implement helper utilities for content formatting

5. Reliability Enhancements
   - [ ] Improve connection state recovery
   - [ ] Add automated reconnection strategies
   - [ ] Enhance error handling with specific solutions
   - [ ] Implement better battery and health monitoring (if supported by the device, events are a bit vague)

6. Code Structure
   - [ ] Split G1Connector into focused components
   - [ ] Add more type hints and dataclasses
   - [ ] Implement async context managers
   - [ ] Add configuration validation


### Medium Priority
   - [ ] Structured telemetry collection
   - [ ] Performance benchmarks
   - [ ] Circuit breakers for problematic operations
   - [ ] Formal dependency injection
   - [ ] Structured logging
   - [ ] Performance optimization
