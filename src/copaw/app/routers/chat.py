# -*- coding: utf-8 -*-
"""Chat API for SaaS frontend - Full agent with tools."""

import uuid
import logging
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


def extract_text_from_msg(msg) -> str:
    """Extract text content from a message, filtering out tool calls and results.
    
    Args:
        msg: Message object from agent
        
    Returns:
        Extracted text content
    """
    if msg is None:
        return ""
    
    text_content = ""
    
    # If msg has content attribute
    if hasattr(msg, 'content'):
        content = msg.content
        
        # If content is a string, check if it's a text chunk
        if isinstance(content, str):
            # Filter out tool_use and tool_result chunks
            if content.startswith("{'type': 'tool_"):
                return ""
            if content.startswith("{'type': 'text'"):
                # Extract text from the chunk
                import re
                match = re.search(r"'text': '([^']*)'", content)
                if match:
                    return match.group(1)
                return ""
            return content
        
        # If content is a list
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get('type') == 'text':
                    text_content += item.get('text', '')
                elif isinstance(item, str):
                    text_content += item
    
    # If msg has text attribute
    elif hasattr(msg, 'text'):
        text_content = msg.text
    
    # If msg is a dict with text
    elif isinstance(msg, dict):
        if msg.get('type') == 'text':
            text_content = msg.get('text', '')
    
    return text_content


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
    msg_count = 0

    try:
        logger.info(f"Starting query handler for session {session_id}")
        async for msg, last in runner.query_handler(
            msgs=[user_msg],
            request=agent_request,
        ):
            msg_count += 1
            
            if msg is not None:
                # Extract text content, filtering out tool calls
                text = extract_text_from_msg(msg)
                if text:
                    full_response += text

        logger.info(f"Query handler completed. Total messages: {msg_count}, Response length: {len(full_response)}")

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

    async def generate():
        try:
            async for msg, last in runner.query_handler(
                msgs=[user_msg],
                request=agent_request,
            ):
                if msg:
                    text = extract_text_from_msg(msg)
                    if text:
                        yield text

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
