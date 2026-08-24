"""
AgentOS SDK Example: Stream Task Execution Events over WebSocket.
"""

import asyncio
import json
import websockets

async def stream_task(task_id: str, host: str = "localhost:8000"):
    uri = f"ws://{host}/api/v1/events/stream/{task_id}"
    print(f"Connecting to execution stream: {uri}")
    
    async with websockets.connect(uri) as ws:
        print("Connected to AgentOS event stream. Listening for events...")
        while True:
            try:
                msg = await ws.recv()
                event = json.loads(msg)
                print(f"[{event.get('timestamp', 'now')}] {event.get('event_type')}: {event.get('payload') or event}")
            except websockets.ConnectionClosed:
                print("Stream completed or connection closed.")
                break

if __name__ == "__main__":
    asyncio.run(stream_task("sample-task-id"))
