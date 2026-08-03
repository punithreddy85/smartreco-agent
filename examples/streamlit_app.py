"""Streamlit Demo App for SmartReco Agent.

This application demonstrates how to integrate with the SmartReco Agent's
simplified streaming API in a Streamlit application. It provides a clean
chat interface with real-time token streaming and message handling.

To run this app:
    streamlit run examples/streamlit_app.py

Make sure the SmartReco Agent server is running on http://localhost:8081
"""

import json
import uuid
from typing import Any, Dict, List

import requests
import streamlit as st


def initialize_session_state():
    """Initialize Streamlit session state variables."""
    if "messages" not in st.session_state:
        st.session_state.messages = []

    if "thread_id" not in st.session_state:
        st.session_state.thread_id = str(uuid.uuid4())

    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())

    if "user_id" not in st.session_state:
        st.session_state.user_id = "streamlit_user"


def stream_agent_response(
    message: str,
    thread_id: str,
    session_id: str,
    user_id: str,
    stream_tokens: bool = True,
    api_url: str = "http://localhost:8081",
) -> tuple[str, List[Dict[str, Any]]]:
    """Stream response from the SmartReco Agent using the simplified API.

    Args:
        message: User's input message
        thread_id: Conversation thread identifier
        session_id: Session identifier
        user_id: User identifier
        stream_tokens: Whether to stream individual tokens
        api_url: Base URL of the SmartReco Agent API

    Returns:
        Tuple of (final_response, all_messages)
    """
    # Prepare request data
    request_data = {
        "message": message,
        "thread_id": thread_id,
        "session_id": session_id,
        "user_id": user_id,
        "stream_tokens": stream_tokens,
    }

    full_response = ""
    all_messages = []

    try:
        # Make streaming request to the simplified API
        response = requests.post(
            f"{api_url}/v1/stream",
            json=request_data,
            stream=True,
            timeout=60,
            headers={"Accept": "text/event-stream"},
        )
        response.raise_for_status()

        # Process the streaming response
        for line in response.iter_lines(decode_unicode=True):
            if not line.strip():
                continue

            # Check for completion marker
            if line.strip() == "[DONE]":
                break

            try:
                # Parse the event
                event = json.loads(line)
                event_type = event.get("type")
                content = event.get("content")

                if event_type == "token" and isinstance(content, str):
                    # Accumulate tokens for real-time display
                    full_response += content

                elif event_type == "message" and isinstance(content, dict):
                    # Store complete messages
                    all_messages.append(content)

                    # If this is the final AI message, use it as the response
                    if content.get("type") == "ai" and content.get("content"):
                        # If we haven't accumulated tokens, use the message content
                        if not full_response:
                            full_response = content["content"]

                elif event_type == "error":
                    st.error(f"Agent Error: {content.get('message', 'Unknown error')}")
                    break

            except json.JSONDecodeError:
                st.warning(f"Failed to parse response line: {line[:100]}...")
                continue

    except requests.exceptions.RequestException as e:
        st.error(f"Failed to connect to agent: {e}")
        return "", []

    return full_response, all_messages


def display_message(message: Dict[str, Any], role: str):
    """Display a message in the chat interface."""
    with st.chat_message(role):
        content = message.get("content", "")

        # Display the main content
        if content:
            st.write(content)

        # Display tool calls if present
        tool_calls = message.get("tool_calls", [])
        if tool_calls:
            with st.expander("🔧 Tool Calls", expanded=False):
                for i, tool_call in enumerate(tool_calls):
                    st.json(
                        {
                            "tool": tool_call.get("name", "unknown"),
                            "args": tool_call.get("args", {}),
                            "id": tool_call.get("id", ""),
                        }
                    )

        # Display metadata if present
        metadata = message.get("response_metadata", {})
        if metadata:
            with st.expander("📊 Metadata", expanded=False):
                st.json(metadata)


def main():
    """Main Streamlit application."""
    st.set_page_config(page_title="SmartReco Agent Chat", page_icon="🤖", layout="wide")

    st.title("🤖 SmartReco Agent Chat")
    st.markdown("Chat with the SmartReco Agent using the simplified streaming API")

    # Initialize session state
    initialize_session_state()

    # Sidebar configuration
    with st.sidebar:
        st.header("Configuration")

        api_url = st.text_input(
            "API URL",
            value="http://localhost:8081",
            help="Base URL of the SmartReco Agent API",
        )

        stream_tokens = st.checkbox(
            "Stream Tokens",
            value=True,
            help="Enable real-time token streaming for faster response display",
        )

        st.divider()

        # Session information
        st.subheader("Session Info")
        st.text(f"Thread ID: {st.session_state.thread_id[:8]}...")
        st.text(f"Session ID: {st.session_state.session_id[:8]}...")
        st.text(f"User ID: {st.session_state.user_id}")

        if st.button("New Conversation"):
            st.session_state.messages = []
            st.session_state.thread_id = str(uuid.uuid4())
            st.rerun()

        st.divider()

        # API test
        st.subheader("API Status")
        try:
            health_response = requests.get(f"{api_url}/health", timeout=5)
            if health_response.status_code == 200:
                st.success("✅ API Connected")
            else:
                st.error(f"❌ API Error: {health_response.status_code}")
        except Exception:
            st.error("❌ API Unreachable, error={e}")

    # Main chat interface
    st.subheader("Chat")

    # Display chat history
    for message in st.session_state.messages:
        if message["role"] == "user":
            with st.chat_message("user"):
                st.write(message["content"])
        else:
            # For agent messages, display the structured content
            display_message(message["content"], "assistant")

    # Chat input
    if prompt := st.chat_input("Ask me anything..."):
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": prompt})

        # Display user message
        with st.chat_message("user"):
            st.write(prompt)

        # Stream agent response
        with st.chat_message("assistant"):
            response_placeholder = st.empty()

            # Show loading spinner
            with st.spinner("Agent is thinking..."):
                # Stream the response
                full_response, all_messages = stream_agent_response(
                    message=prompt,
                    thread_id=st.session_state.thread_id,
                    session_id=st.session_state.session_id,
                    user_id=st.session_state.user_id,
                    stream_tokens=stream_tokens,
                    api_url=api_url,
                )

            # Display the final response
            if full_response:
                response_placeholder.write(full_response)

                # Add to chat history
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": {
                            "type": "ai",
                            "content": full_response,
                            "messages": all_messages,  # Store all messages for debugging
                        },
                    }
                )
            else:
                response_placeholder.error("No response received from agent")

    # Advanced features in expander
    with st.expander("🔧 Advanced Features", expanded=False):
        st.subheader("Raw Session Data")

        col1, col2 = st.columns(2)

        with col1:
            st.text("Session State:")
            st.json(
                {
                    "thread_id": st.session_state.thread_id,
                    "session_id": st.session_state.session_id,
                    "user_id": st.session_state.user_id,
                    "message_count": len(st.session_state.messages),
                }
            )

        with col2:
            st.text("Last Message Details:")
            if st.session_state.messages:
                st.json(st.session_state.messages[-1])

        # Export conversation
        if st.button("Export Conversation"):
            conversation_data = {
                "thread_id": st.session_state.thread_id,
                "session_id": st.session_state.session_id,
                "user_id": st.session_state.user_id,
                "messages": st.session_state.messages,
                "export_timestamp": str(uuid.uuid4()),
            }

            st.download_button(
                label="Download Conversation JSON",
                data=json.dumps(conversation_data, indent=2),
                file_name=f"conversation_{st.session_state.thread_id[:8]}.json",
                mime="application/json",
            )


if __name__ == "__main__":
    main()
