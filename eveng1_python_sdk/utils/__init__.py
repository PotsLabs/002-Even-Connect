"""Utility functions and constants for G1 glasses SDK"""

from utils.logger import setup_logger, user_guidance
from utils.constants import (
    UUIDS, COMMANDS, EventCategories, StateEvent, 
    ConnectionState, StateColors, StateDisplay
)

__all__ = [
    'setup_logger',
    'user_guidance',
    'UUIDS',
    'COMMANDS',
    'EventCategories',
    'StateEvent',
    'ConnectionState',
    'StateColors',
    'StateDisplay'
] 