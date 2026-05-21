"""
Even AI interaction example

documentation: (also see microphone.py as mic is relevant to AI too)

Start Even AI
Command Information
Command: 0xF5
subcmd (Sub-command): 0~255
param (Parameters): Specific parameters associated with each sub-command.
Sub-command Descriptions
subcmd: 0 (exit to dashboard manually).
Description: Stop all advanced features and return to the dashboard.
subcmd: 1 (page up/down control in manual mode).
Description: page-up(left ble) / page-down (right ble)
subcmd: 23 （start Even AI).
Description: Notify phone to activate Even AI.
subcmd: 24 （stop Even AI recording).
Description: Even AI recording ended.

Send AI Result
Command Information
Command: 0x4E
seq (Sequence Number): 0~255
total_package_num (Total Package Count): 1~255
current_package_num (Current Package Number): 0~255
newscreen (Screen Status)
Field Descriptions
seq (Sequence Number):

Range: 0~255
Description: Indicates the sequence of the current package.
total_package_num (Total Package Count):

Range: 1~255
Description: The total number of packages being sent in this transmission.
current_package_num (Current Package Number):

Range: 0~255
Description: The current package number within the total, starting from 0.
newscreen (Screen Status):

Composed of lower 4 bits and upper 4 bits to represent screen status and Even AI mode.
Lower 4 Bits (Screen Action):
0x01: Display new content
Upper 4 Bits (Even AI Status):
0x30: Even AI displaying（automatic mode default）
0x40: Even AI display complete (Used when the last page of automatic mode)
0x50: Even AI manual mode
0x60: Even AI network error
Example:
New content + Even AI displaying state is represented as 0x31.
new_char_pos0 and new_char_pos1:

new_char_pos0: Higher 8 bits of the new character position.
new_char_pos1: Lower 8 bits of the new character position.
current_page_num (Current Page Number):

Range: 0~255
Description: Represents the current page number.
max_page_num (Maximum Page Number):

Range: 1~255
Description: The total number of pages.
data (Data):

Description: The actual data being transmitted in this package.

"""

import asyncio
from connector import G1Connector
from services import AudioService

async def main():
    glasses = G1Connector()
    await glasses.connect()
    audio = AudioService(glasses)
    # Even AI example 