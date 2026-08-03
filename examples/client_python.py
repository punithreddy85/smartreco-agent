"""Python client example for SmartReco Agent simplified streaming API.

This module provides a simple Python client for interacting with the
SmartReco Agent's streaming API, demonstrating how to handle real-time
responses and different event types.

Usage:
    python examples/client_python.py

    Or use as a library:
    from examples.client_python import SmartRecoAgentClient

    client = SmartRecoAgentClient()
    await client.stream_chat("Hello, world!", "thread-123", "session-123", "user-123")
"""

import asyncio
import json
import uuid
from typing import Any, AsyncGenerator, Dict, Optional

import aiohttp


class SmartRecoAgentClient:
    """Async Python client for SmartReco Agent streaming API."""

    def __init__(
        self,
        base_url: str = "http://localhost:8081",
        headers: Optional[Dict[str, str]] = None,
    ):
        """Initialize the client.

        Args:
            base_url: Base URL of the SmartReco Agent API
            headers: Optional additional headers (e.g., for authentication)
        """
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            **(headers or {}),
        }

    async def stream_chat(
        self,
        message: str,
        thread_id: str,
        session_id: str,
        user_id: str,
        stream_tokens: bool = True,
        timeout: int = 60,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream a chat conversation with the agent.

        Args:
            message: User's input message
            thread_id: Conversation thread identifier
            session_id: Session identifier
            user_id: User identifier
            stream_tokens: Whether to stream individual tokens
            timeout: Request timeout in seconds

        Yields:
            Event dictionaries with 'type' and 'content' fields
        """
        request_data = {
            "message": message,
            "thread_id": thread_id,
            "session_id": session_id,
            "user_id": user_id,
            "stream_tokens": stream_tokens,
        }

        timeout_config = aiohttp.ClientTimeout(total=timeout)

        async with aiohttp.ClientSession(timeout=timeout_config) as session:
            async with session.post(
                f"{self.base_url}/v1/stream", json=request_data, headers=self.headers
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"HTTP {response.status}: {error_text}")

                # Stream the response line by line
                async for line in response.content:
                    line_str = line.decode("utf-8").strip()

                    if not line_str:
                        continue

                    # Check for completion marker
                    if line_str == "[DONE]":
                        break

                    try:
                        event = json.loads(line_str)
                        yield event
                    except json.JSONDecodeError:
                        # Skip invalid JSON lines
                        continue

    async def send_message(
        self,
        message: str,
        thread_id: Optional[str] = None,
        session_id: Optional[str] = None,
        user_id: str = "python_client",
        stream_tokens: bool = True,
    ) -> tuple[str, list[Dict[str, Any]]]:
        """Send a message and return the complete response.

        Args:
            message: User's input message
            thread_id: Optional thread ID (generated if not provided)
            session_id: Optional session ID (uses thread_id if not provided)
            user_id: User identifier
            stream_tokens: Whether to stream individual tokens

        Returns:
            Tuple of (final_response_text, all_messages)
        """
        # Generate IDs if not provided
        if thread_id is None:
            thread_id = str(uuid.uuid4())
        if session_id is None:
            session_id = thread_id

        full_response = ""
        all_messages = []

        async for event in self.stream_chat(
            message, thread_id, session_id, user_id, stream_tokens
        ):
            event_type = event.get("type")
            content = event.get("content")

            if event_type == "token" and isinstance(content, str):
                # Accumulate tokens
                full_response += content

            elif event_type == "message" and isinstance(content, dict):
                # Store complete messages
                all_messages.append(content)

                # If this is the final AI message, use it as the response
                if content.get("type") == "ai" and content.get("content"):
                    if not full_response:  # Use message content if no tokens received
                        full_response = content["content"]

            elif event_type == "error":
                error_msg = (
                    content.get("message", "Unknown error")
                    if isinstance(content, dict)
                    else str(content)
                )
                raise Exception(f"Agent error: {error_msg}")

        return full_response, all_messages

    async def check_health(self) -> Dict[str, Any]:
        """Check if the API is healthy."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/health") as response:
                if response.status == 200:
                    return await response.json()
                else:
                    raise Exception(f"Health check failed: HTTP {response.status}")


async def example_streaming_chat():
    """Example of streaming chat with token updates."""
    print("🤖 SmartReco Agent - Python Client Example")
    print("=" * 50)

    client = SmartRecoAgentClient()

    # Check if API is available
    try:
        health = await client.check_health()
        print(f"✅ API Status: {health.get('status', 'unknown')}")
    except Exception as e:
        print(f"❌ API Health Check Failed: {e}")
        return

    # Generate session IDs
    thread_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    user_id = "python_example_user"

    print("\n📱 Session Info:")
    print(f"Thread ID: {thread_id}")
    print(f"Session ID: {session_id}")
    print(f"User ID: {user_id}")

    # Example conversation
    messages = [
        "Hello! Can you help me with some math?",
        "What is 15 * 24?",
        "Can you explain how you calculated that?",
    ]

    for i, message in enumerate(messages, 1):
        print(f"\n{'=' * 50}")
        print(f"Message {i}: {message}")
        print(f"{'=' * 50}")

        print("\n🔄 Streaming Response:")
        full_response = ""
        message_count = 0

        try:
            async for event in client.stream_chat(
                message=message,
                thread_id=thread_id,
                session_id=session_id,
                user_id=user_id,
                stream_tokens=True,
            ):
                event_type = event.get("type")
                content = event.get("content")

                if event_type == "token":
                    # Print tokens in real-time
                    print(content, end="", flush=True)
                    full_response += content

                elif event_type == "message":
                    message_count += 1
                    msg_type = (
                        content.get("type", "unknown")
                        if isinstance(content, dict)
                        else "unknown"
                    )

                    # Print message info
                    if msg_type == "tool":
                        tool_id = content.get("tool_call_id", "unknown")
                        tool_content = content.get("content", "")
                        print(f"\n🔧 Tool Result [{tool_id}]: {tool_content}")
                    elif msg_type == "ai" and content.get("tool_calls"):
                        tool_calls = content.get("tool_calls", [])
                        print(f"\n🔧 Tool Calls: {len(tool_calls)} tools invoked")
                        for tool_call in tool_calls:
                            print(
                                f"   - {tool_call.get('name', 'unknown')}: {tool_call.get('args', {})}"
                            )

                elif event_type == "error":
                    error_msg = (
                        content.get("message", "Unknown error")
                        if isinstance(content, dict)
                        else str(content)
                    )
                    print(f"\n❌ Error: {error_msg}")

        except Exception as e:
            print(f"\n❌ Stream Error: {e}")
            continue

        print("\n\n📊 Summary:")
        print(f"   - Final response length: {len(full_response)} characters")
        print(f"   - Messages received: {message_count}")

        # Wait before next message
        if i < len(messages):
            print("\n⏳ Waiting 2 seconds before next message...")
            await asyncio.sleep(2)


async def example_simple_chat():
    """Example of simple chat without streaming tokens."""
    print("\n🔹 Simple Chat Example (No Token Streaming)")
    print("=" * 50)

    client = SmartRecoAgentClient()

    try:
        response, messages = await client.send_message(
            "What's the weather like in a general sense?", stream_tokens=False
        )

        print(f"📝 Response: {response}")
        print(f"📊 Total messages: {len(messages)}")

        for i, msg in enumerate(messages):
            msg_type = msg.get("type", "unknown")
            content = msg.get("content", "")
            print(
                f"   {i + 1}. [{msg_type}] {content[:100]}{'...' if len(content) > 100 else ''}"
            )

    except Exception as e:
        print(f"❌ Error: {e}")


async def main():
    """Run all examples."""
    try:
        # Run streaming example
        await example_streaming_chat()

        # Run simple example
        await example_simple_chat()

    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
