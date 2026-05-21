"""
Example of sending text to G1 glasses
"""
import asyncio
from connector import G1Connector
from utils.logger import setup_logger

async def main():
    """Test sequence with different text display methods"""
    logger = setup_logger()
    glasses = G1Connector()
    
    # Test texts
    single_text = "This is a single text that will display for 5 seconds."
    indefinite_text = "This text will display until manually cleared."
    large_text = """Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do 
    eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim 
    veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo 
    consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse 
    cillum dolore eu fugiat nulla pariatur."""
    
    text_sequence = [
        "First text in sequence",
        "Second text in sequence",
        "Third and final text"
    ]
    
    logger.info("Connecting to glasses...")
    await glasses.connect()
    logger.info("Connected! Starting tests...")
    
    try:
        # Test 1: Single text with auto-exit
        logger.info("\n=== Test 1: Single Text with 5s Duration ===")
        await glasses.display.display_text(single_text, hold_time=5)
        
        await asyncio.sleep(2)  # Pause between tests
        
        # Test 2: Text sequence
        logger.info("\n=== Test 2: Text Sequence ===")
        await glasses.display.display_text_sequence(text_sequence, hold_time=3)
        
        await asyncio.sleep(2)
        
        # Test 3: Large text auto-split
        logger.info("\n=== Test 3: Large Text Auto-split ===")
        await glasses.display.display_text(large_text, hold_time=4)
        
        await asyncio.sleep(2)
        
        # Test 4: Indefinite display
        logger.info("\n=== Test 4: Indefinite Display ===")
        await glasses.display.display_text(indefinite_text)
        logger.info("Text will display until manually cleared...")
        await asyncio.sleep(10)  # Simulate some time passing
        
        # Show exit message
        logger.info("\n=== Showing Exit Message ===")
        await glasses.display.show_exit_message()
        
    finally:
        logger.info("Disconnecting...")
        await glasses.disconnect()
        logger.info("Test complete")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExited by user")
    except Exception as e:
        print(f"\nError: {e}")
