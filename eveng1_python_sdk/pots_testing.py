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
