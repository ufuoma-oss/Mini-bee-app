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
        input=[user_message],  # Message for AgentRequest
        session_id=session_id,
        user_id="web_user",  # Default user for web frontend
        stream=False,
    )

    # Process through the agent
    full_response = ""
    msg_count = 0

    try:
        logger.info(f"Starting query handler for session {session_id}")
        async for msg, last in runner.query_handler(
            msgs=[user_msg],  # Msg for agent processing
            request=agent_request,
        ):
            msg_count += 1
            logger.debug(f"Received msg #{msg_count}: {type(msg)}, last={last}")
            
            if msg is not None:
                # Try different ways to extract content
                content = None
                
                # Try msg.content as string
                if hasattr(msg, 'content'):
                    if isinstance(msg.content, str):
                        content = msg.content
                    elif isinstance(msg.content, list):
                        # Handle list content
                        content = " ".join(str(c) for c in msg.content if c)
                
                # Try msg.text
                if not content and hasattr(msg, 'text'):
                    content = msg.text
                
                # Try str(msg)
                if not content:
                    content = str(msg) if msg else ""
                
                if content:
                    full_response += content
                    logger.debug(f"Added content: {content[:100]}...")

        logger.info(f"Query handler completed. Total messages: {msg_count}, Response length: {len(full_response)}")

        if not full_response:
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
        user_id="web_user",  # Default user for web frontend
        stream=True,
    )

    async def generate():
        try:
            async for msg, last in runner.query_handler(
                msgs=[user_msg],
                request=agent_request,
            ):
                if msg:
                    if hasattr(msg, 'content') and isinstance(msg.content, str):
                        yield msg.content
                    elif hasattr(msg, 'text'):
                        yield msg.text

            # Send session ID at the end
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
