# -*- coding: utf-8 -*-
"""Chat API for SaaS frontend - Full agent with tools."""

import uuid
import json
import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["chat"])


class ChatRequest(BaseModel):
    """Chat request from frontend."""

    message: str = Field(..., description="User message")
    session_id: Optional[str] = Field(None, description="Session ID for conversation continuity")
    context: Optional[dict] = Field(None, description="Optional context (documents, etc.)")


class ChatResponse(BaseModel):
    """Chat response for frontend."""

    response: str = Field(..., description="AI response text")
    session_id: str = Field(..., description="Session ID for future requests")


def get_runner(request: Request):
    """Get the runner from app state."""
    runner = getattr(request.app.state, "runner", None)
    if runner is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Runner not initialized")
    return runner


def extract_text_content(msg) -> str:
    """Extract text content from a message.
    
    The agent returns messages in various formats:
    - Dict with {'type': 'text', 'text': 'content'}
    - String representation of dict
    - Msg object with content attribute
    
    Args:
        msg: Message from agent
        
    Returns:
        Extracted text content
    """
    if msg is None:
        return ""
    
    # Convert to string to handle all cases
    msg_str = str(msg)
    
    # Pattern to match text content in the response
    # The format is: {'type': 'text', 'text': 'actual text here'}
    pattern = r"\{'type':\s*'text',\s*'text':\s*'(.*?)'\}"
    
    matches = re.findall(pattern, msg_str, re.DOTALL)
    
    if matches:
        # Get the last match (most complete text)
        text = matches[-1]
        # Unescape any escaped characters
        text = text.replace("\\n", "\n").replace("\\'", "'").replace('\\"', '"')
        return text
    
    # If no matches, try to extract from dict-like format
    if "text" in msg_str and "type" in msg_str:
        try:
            # Try to parse as JSON (replacing single quotes with double quotes)
            json_str = msg_str.replace("'", '"')
            data = json.loads(json_str)
            if isinstance(data, dict) and data.get("type") == "text":
                return data.get("text", "")
        except:
            pass
    
    # Check if it's a Msg object with content
    if hasattr(msg, 'content'):
        content = msg.content
        if isinstance(content, str):
            # Check if it's a text type message
            if content.startswith("{'type': 'text'"):
                match = re.search(r"'text':\s*'(.*?)'\s*\}", content, re.DOTALL)
                if match:
                    return match.group(1).replace("\\n", "\n")
            return content
    
    return ""


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    runner = Depends(get_runner),
):
    """Send a message and get an AI response.

    This is the main endpoint for the SaaS frontend to chat with the AI agent.
    The agent has access to tools for file operations, shell commands, browser, etc.
    """
    from agentscope.message import Msg
    from agentscope_runtime.engine.schemas.agent_schemas import (
        AgentRequest,
        Message,
        TextContent,
    )

    # Generate or use existing session ID
    session_id = request.session_id or str(uuid.uuid4())

    # Build the message using agentscope Msg (which the agent expects)
    user_msg = Msg(name="user", content=request.message, role="user")

    # Also create a Message for AgentRequest
    user_message = Message(
        role="user",
        type="message",
        content=[TextContent(text=request.message)],
    )

    # Create agent request with user_id
    agent_request = AgentRequest(
        input=[user_message],
        session_id=session_id,
        user_id="web_user",
        stream=False,
    )

    # Process through the agent
    full_response = ""
    last_text = ""

    try:
        logger.info(f"Starting query handler for session {session_id}")
        async for msg, last in runner.query_handler(
            msgs=[user_msg],
            request=agent_request,
        ):
            if msg is not None:
                # Extract text from the message
                text = extract_text_content(msg)
                if text and len(text) > len(last_text):
                    # Only update if we got more text (streaming)
                    last_text = text

        # Use the last extracted text as the full response
        full_response = last_text

        logger.info(f"Query handler completed. Response length: {len(full_response)}")

        if not full_response.strip():
            full_response = "I apologize, but I couldn't generate a response. Please try again."

    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        logger.error(f"Chat error: {e}\n{error_detail}")
        full_response = f"I encountered an error: {str(e)}. Please try again."

    return ChatResponse(
        response=full_response,
        session_id=session_id,
    )


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    runner = Depends(get_runner),
):
    """Stream a chat response.

    Returns the response as a stream of text chunks.
    """
    from agentscope.message import Msg
    from agentscope_runtime.engine.schemas.agent_schemas import (
        AgentRequest,
        Message,
        TextContent,
    )

    session_id = request.session_id or str(uuid.uuid4())

    user_msg = Msg(name="user", content=request.message, role="user")
    user_message = Message(
        role="user",
        type="message",
        content=[TextContent(text=request.message)],
    )

    agent_request = AgentRequest(
        input=[user_message],
        session_id=session_id,
        user_id="web_user",
        stream=True,
    )

    last_text = ""

    async def generate():
        nonlocal last_text
        try:
            async for msg, last in runner.query_handler(
                msgs=[user_msg],
                request=agent_request,
            ):
                if msg:
                    text = extract_text_content(msg)
                    if text and len(text) > len(last_text):
                        # Yield only the new part
                        new_text = text[len(last_text):]
                        yield new_text
                        last_text = text

            yield f"\n\n---SESSION_ID:{session_id}---"

        except Exception as e:
            yield f"Error: {str(e)}"

    return StreamingResponse(
        generate(),
        media_type="text/plain",
        headers={
            "X-Session-ID": session_id,
        },
    )
