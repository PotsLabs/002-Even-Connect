"""
PowerPoint teleprompter example for G1 glasses
Displays speaker notes from active PowerPoint presentation
"""
import asyncio
import sys
from connector import G1Connector
from utils.logger import setup_logger


print("Script starting...")

async def main():
    """Run PowerPoint teleprompter"""
    logger = setup_logger()
    print("Logger setup complete")
    
    # Initialize G1 connection
    glasses = G1Connector()
    logger.info("Connecting to glasses...")
    await glasses.connect()
    logger.info("Connected to glasses!")
    
    try:
        print("Attempting win32com import...")
        import win32com.client
        print("win32com imported successfully")
        
        # Initialize PowerPoint
        powerpoint = win32com.client.Dispatch("PowerPoint.Application")
        
        # Track current state
        current_slide = None
        current_notes = None
        notes_cache = {}  # Add cache for slide notes
        
        while True:
            try:
                # Get current slide info
                if powerpoint.SlideShowWindows.Count > 0:
                    # Slideshow mode
                    slideshow = powerpoint.SlideShowWindows(1)
                    slide_number = slideshow.View.CurrentShowPosition
                    current_slide_obj = powerpoint.ActivePresentation.Slides(slide_number)
                else:
                    # Normal mode
                    slide = powerpoint.ActiveWindow.View.Slide
                    slide_number = slide.SlideNumber
                    current_slide_obj = slide
                
                # Only process if slide changed
                if slide_number != current_slide:
                    current_slide = slide_number
                    
                    # Check cache first
                    if slide_number in notes_cache:
                        notes_text = notes_cache[slide_number]
                    else:
                        # Get notes using the working method
                        notes_text = ""
                        if current_slide_obj.HasNotesPage:
                            notes_page = current_slide_obj.NotesPage
                            # Get text from all shapes in notes page
                            for shape in notes_page.Shapes:
                                if shape.HasTextFrame:
                                    text = shape.TextFrame.TextRange.Text.strip()
                                    # Filter out standalone slide numbers
                                    if text and text != str(slide_number):
                                        notes_text += text + "\n"
                    
                        notes_text = notes_text.strip()
                        notes_cache[slide_number] = notes_text  # Cache the result
                    
                    if notes_text and notes_text != current_notes:
                        current_notes = notes_text
                        logger.debug(f"Notes for Slide {slide_number}")
                        # Let display service handle text formatting and chunking
                        await glasses.display.display_text(notes_text)
                            
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                
            await asyncio.sleep(0.1)
            
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        logger.info("Stopping monitor...")
        await glasses.display.show_exit_message()
        await glasses.disconnect()
        logger.info("Monitor stopped")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExited by user")
    except Exception as e:
        print(f"\nError: {e}") 