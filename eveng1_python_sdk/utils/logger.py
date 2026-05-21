"""Logging utilities for G1 glasses SDK"""
import os
import logging
import sys
from rich.console import Console
from rich.logging import RichHandler
from typing import Optional
from utils.config import Config

# Global console instance
_console: Optional[Console] = None
_dashboard_mode: bool = False

def get_console() -> Console:
    """Get or create global console instance"""
    global _console
    if _console is None:
        _console = Console()
    return _console

def set_dashboard_mode(enabled: bool):
    """Toggle dashboard mode to suppress console output"""
    global _dashboard_mode
    _dashboard_mode = enabled

def setup_logger(config: Optional[Config] = None) -> logging.Logger:
    """Set up logger with rich handler"""
    # Create logger
    logger = logging.getLogger("G1")
    
    if not logger.handlers:  # Only add handlers if none exist
        # Set base level to DEBUG to capture everything
        logger.setLevel(logging.DEBUG)
        
        # Clear any existing handlers
        logger.handlers.clear()
        
        # Prevent propagation to root logger
        logger.propagate = False
        
        # File handler - logs everything with detailed formatting
        if config and config.log_file:
            os.makedirs(os.path.dirname(config.log_file), exist_ok=True)
            mode = 'w' if getattr(config, 'reset_logs', True) else 'a'
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
            )
            file_handler = logging.FileHandler(config.log_file, mode=mode)
            file_handler.setFormatter(file_formatter)
            file_handler.setLevel(logging.DEBUG)  # Log everything to file
            logger.addHandler(file_handler)

        # Console handler with rich formatting
        if config and config.console_log:
            console_handler = RichHandler(
                rich_tracebacks=True,
                markup=True,
                show_time=False,  # Time shown in file logs only
                show_path=False,  # Path shown in file logs only
                console=Console(force_terminal=True)
            )
            
            # Custom emit method to handle dashboard mode
            original_emit = console_handler.emit
            def custom_emit(record):
                if not _dashboard_mode:
                    original_emit(record)
            console_handler.emit = custom_emit
            
            # Set console level from config or default to INFO
            level = logging.INFO if not config else getattr(config, 'log_level', logging.INFO)
            console_handler.setLevel(level)
            logger.addHandler(console_handler)
        
        # Add convenience methods
        def success(self, message: str):
            """Log success message in green"""
            plain_msg = message.replace("[green]", "").replace("[/green]", "")
            self.info(plain_msg, extra={"markup": False})  # For file log
            self.info(f"[green]{message}[/green]", extra={"markup": True})  # For console
            
        def user(self, message: str):
            """Log user-friendly message in yellow"""
            plain_msg = message.replace("[yellow]", "").replace("[/yellow]", "")
            self.info(plain_msg, extra={"markup": False})  # For file log
            self.info(f"[yellow]{message}[/yellow]", extra={"markup": True})  # For console
            
        def debug_raw(self, message: str):
            """Log raw debug data"""
            self.debug(message)  # Goes to file only due to level
            
        logger.success = success.__get__(logger)
        logger.user = user.__get__(logger)
        logger.debug_raw = debug_raw.__get__(logger)
        
    return logger

def user_guidance(logger: logging.Logger, message: str):
    """Log user guidance messages without duplication"""
    # Only log once, with markup for console and plain for file
    logger.info(message, extra={"markup": True})  # Console gets formatted
    
    # If we have file logging enabled, log without markup
    if any(isinstance(h, logging.FileHandler) for h in logger.handlers):
        plain_msg = message.replace("[yellow]", "").replace("[/yellow]", "")
        plain_msg = plain_msg.replace("[green]", "").replace("[/green]", "")
        plain_msg = plain_msg.replace("[red]", "").replace("[/red]", "")
        logger.debug(plain_msg, extra={"markup": False})  # File gets plain text 