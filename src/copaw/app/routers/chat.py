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


def extract_final_text(msg) -> str:
    """Extract the final complete text from a streaming message.
    
    The agent returns streaming messages in format:
    {'type': 'text', 'text': 'Hello'}
    {'type': 'text', 'text': 'Hello!'}
    {'type': 'text', 'text': 'Hello! How'}
    ...
    
    Each message contains the accumulated text so far.
    We need to extract the LAST complete text value.
    
    Args:
        msg: Message from agent
        
    Returns:
        The final complete text content
    """
    if msg is None:
        return ""
    
    msg_str = str(msg)
    
    # Pattern to match text content: 'text': 'content'
    # We want to find ALL occurrences and take the LAST one (most complete)
    # The pattern captures text between 'text': ' and the closing '
    # We need to handle multi-line text with escaped characters
    
    # Find all text values
    pattern = r"'text':\s*'(.*?)(?='\s*[,}]|\s*$)"
    matches = re.findall(pattern, msg_str, re.DOTALL)
    
    if matches:
        # Get the last match (most complete text)
        text = matches[-1]
        # Unescape characters
        text = text.replace("\\n", "\n").replace("\\'", "'").replace('\\"', '"').replace("\\\\", "\\")
        return text
    
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
        stream=False,
    )

    final_response = ""

    try:
        logger.info(f"Starting query handler for session {session_id}")
        async for msg, last in runner.query_handler(
            msgs=[user_msg],
            request=agent_request,
        ):
            if msg is not None and last:
                # Only extract text from the final message
                final_response = extract_final_text(msg)

        logger.info(f"Query handler completed. Response length: {len(final_response)}")

        if not final_response.strip():
            final_response = "I apologize, but I couldn't generate a response. Please try again."

    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        logger.error(f"Chat error: {e}\n{error_detail}")
        final_response = f"I encountered an error: {str(e)}. Please try again."

    return ChatResponse(
        response=final_response,
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
                    text = extract_final_text(msg)
                    if len(text) > len(last_text):
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
