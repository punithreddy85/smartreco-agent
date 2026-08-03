# SmartReco Agent Client Examples

This directory contains client examples demonstrating how to interact with the SmartReco Agent's simplified streaming API. These examples show best practices for handling real-time streaming, different event types, and error scenarios.

## 📁 Available Examples

### 1. Streamlit Demo App (`streamlit_app.py`)

A full-featured chat application built with Streamlit:
- **Real-time chat interface** with message history
- **Token streaming visualization** for responsive UX
- **Session management** with thread and session persistence
- **Configuration panel** for API settings and debugging
- **Export functionality** for conversation data

**Key Features:**
- Live token streaming with visual updates
- Tool call visualization with expandable details
- API health monitoring
- Conversation export to JSON
- Session state management

**To Run:**
```bash
# Install Streamlit if not already installed
pip install streamlit requests

# Run the app
streamlit run examples/streamlit_app.py

# Open http://localhost:8501 in your browser
```

### 2. Python Async Client (`client_python.py`)

A robust async Python client for server-to-server communication:
- **Async/await support** using aiohttp
- **Streaming and non-streaming modes** for different use cases
- **Comprehensive error handling** with detailed error messages
- **Session management** with automatic ID generation
- **Health checking** for API availability

**Key Features:**
- Generator-based streaming for memory efficiency
- Automatic session ID generation
- Built-in retry logic and timeout handling
- Example conversation flows

**To Run:**
```bash
# Install dependencies
pip install aiohttp

# Run the example
python examples/client_python.py
```

**Usage as Library:**
```python
from examples.client_python import SmartRecoAgentClient

client = SmartRecoAgentClient()

# Simple message
response, messages = await client.send_message("Hello!")

# Streaming chat
async for event in client.stream_chat("Hello!", "thread-123", "session-123", "user-123"):
    if event['type'] == 'token':
        print(event['content'], end='', flush=True)
```

## 🔗 API Reference

### Request Format

All clients use the simplified request format:

```json
{
  "message": "User's input message",
  "thread_id": "Conversation thread identifier",
  "session_id": "Session identifier",
  "user_id": "User identifier",
  "stream_tokens": true
}
```

### Response Format

The API returns Server-Sent Events with this format:

```json
{"type": "message", "content": {"type": "ai", "content": "Hello"}}
{"type": "token", "content": " world"}
{"type": "error", "content": {"message": "Error occurred", "recoverable": false}}
[DONE]
```

**Event Types:**
- `message` - Complete messages (AI responses, tool calls, tool results)
- `token` - Individual tokens for real-time streaming
- `error` - Error messages with recovery information
- `[DONE]` - Stream completion marker

## 🚀 Getting Started

### Prerequisites

1. **SmartReco Agent Server Running**
   ```bash
   # Start the SmartReco Agent server
   cd smartreco-agent
   python -m uvicorn smartreco_agent.src.main:app --reload --port 8081
   ```

2. **Install Client Dependencies**
   ```bash
   # For Python examples
   pip install aiohttp requests streamlit

   # For TypeScript example
   npm install # (if using in a Node.js project)
   ```

### Quick Test

Test the API is working:

```bash
# Health check
curl http://localhost:8081/health

# Simple streaming test
curl -X POST 'http://localhost:8081/stream' \
  -H 'Content-Type: application/json' \
  -H 'Accept: text/event-stream' \
  -d '{
    "message": "Hello!",
    "thread_id": "test-123",
    "session_id": "test-123",
    "user_id": "test-user",
    "stream_tokens": true
  }'
```

## 🎯 Best Practices

### 1. Session Management
- Use consistent `thread_id` for multi-turn conversations
- Use `session_id` to group related threads
- Generate UUIDs for unique identifiers

### 2. Error Handling
- Always handle `error` events in streams
- Check `recoverable` flag to determine retry logic
- Implement timeout and connection error handling

### 3. Token Streaming
- Set `stream_tokens: true` for real-time UX
- Set `stream_tokens: false` for simpler message-only handling
- Buffer tokens appropriately for UI updates

### 4. Performance
- Use appropriate timeouts for your use case
- Handle stream interruption gracefully
- Consider connection pooling for high-volume usage

## 🔧 Enterprise Features

All examples preserve enterprise features from the original implementation:

- **SSO Authentication**: Pass `X-Token` header for enterprise auth
- **Langfuse Tracing**: Automatic tracing and analytics
- **PostgreSQL Persistence**: Conversation history and checkpointing
- **Error Monitoring**: Comprehensive error logging and recovery

## 📚 Additional Resources

- [SmartReco Agent API Documentation](../README.md)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Streamlit Documentation](https://docs.streamlit.io/)
- [LangGraph Documentation](https://python.langchain.com/docs/langgraph)

## 🐛 Troubleshooting

### Common Issues

**Connection Refused**
- Ensure SmartReco Agent server is running on http://localhost:8081
- Check firewall settings and port availability

**Authentication Errors**
- Verify SSO token is valid (if using enterprise features)
- Check X-Token header format

**Streaming Issues**
- Ensure `Accept: text/event-stream` header is set
- Check for proxy/firewall interference with streaming
- Verify timeout settings are appropriate

**Token Streaming Not Working**
- Confirm `stream_tokens: true` in request
- Check for buffering issues in HTTP clients
- Verify WebSocket/EventSource compatibility

### Debug Mode

Enable detailed logging in examples:

```python
# Python examples
import logging
logging.basicConfig(level=logging.DEBUG)

# Streamlit
st.set_option('client.showErrorDetails', True)
```

For more help, check the main project documentation or create an issue in the repository.
