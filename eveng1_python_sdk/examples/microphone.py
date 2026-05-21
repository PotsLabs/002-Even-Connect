"""
Example of using G1 glasses microphone
note: can we capture the audio, real-time transcribe it, then show it as output from the script? (this would enable usecases such as custom AI and search)


from the documentation:
Open Glasses Mic
Command Information
Command: 0x0E
enable:
0 (Disable) / 1 (Enable)
Description
enable:
0: Disable the MIC (turn off sound pickup).
1: Enable the MIC (turn on sound pickup).
Response from Glasses
Command: 0x0E
rsp_status (Response Status):
0xC9: Success
0xCA: Failure
enable:
0: MIC disabled.
1: MIC enabled.
Example
Command sent to device: 0x0E, with enable = 1 to enable the MIC.
Device response:
If successful: 0x0E with rsp_status = 0xC9 and enable = 1.
If failed: 0x0E with rsp_status = 0xCA and enable = 1.
Receive Glasses Mic data
Command Information
Command: 0xF1
seq (Sequence Number): 0~255
data (Audio Data): Actual MIC audio data being transmitted.
Field Descriptions
seq (Sequence Number):
Range: 0~255
Description: This is the sequence number of the current data packet. It helps to ensure the order of the audio data being received.
data (Audio Data):
Description: The actual audio data captured by the MIC, transmitted in chunks according to the sequence.
Example
Command: 0xF1, with seq = 10 and data = [Audio Data]
Description: This command transmits a chunk of audio data from the glasses' MIC, with a sequence number of 10 to maintain packet order.
"""

import asyncio
from connector import G1Connector
from services import AudioService

async def main():
    """
    Demonstrates microphone activation and audio streaming
    
    Protocol details:
    - Uses right-side microphone
    - Activated with command 0x0E
    - Receives LC3 format audio stream
    - Maximum recording duration: 30 seconds
    """
    glasses = G1Connector()
    await glasses.connect()
    
    audio = AudioService(glasses)
    await audio.start_recording()
    # Record for 5 seconds
    await asyncio.sleep(5)
    await audio.stop_recording()

if __name__ == "__main__":
    asyncio.run(main())
