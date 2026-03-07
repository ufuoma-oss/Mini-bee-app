# -*- coding: utf-8 -*-
"""Chat API for SaaS frontend - Full agent with tools."""

import uuid
import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["chat"])

class ChatRequest(BaseModel):
    message: str = Field(..., description="User message")
    session_id: Optional[str] = Field(None, description="Session ID")
    context: Optional[dict] = Field(None, description="Optional context")

class ChatResponse(BaseModel):
    response: str = Field(..., description="AI response")
    session_id: str = Field(..., description="Session ID")

def get_runner(request: Request):
    runner = getattr(request.app.state, "runner", None)
    if runner is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Runner not initialized")
    return runner

def extract_final_text(msg) -> str:
    if msg is None:
        return ""
    msg_str = str(msg)
    pattern = r"'text':s*'(.*?)(?='s*[,}]|s*$)"
    matches = re.findall(pattern, msg_str, re.DOTALL)
    if matches:
        text = matches[-1]
        return text.replace("\n", "
").replace("\'", "'").replace('\"', '"').replace("\\", "\")
    return ""

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, runner = Depends(get_runner)):
    """Send a message and get an AI response."""
    from agentscope.message import Msg
    from agentscope_runtime.engine.schemas.agent_schemas import AgentRequest, Message, TextContent

    session_id = request.session_id or str(uuid.uuid4())
    user_msg = Msg(name="user", content=request.message, role="user")
    user_message = Message(role="user", type="message", content=[TextContent(text=request.message)])
    agent_request = AgentRequest(input=[user_message], session_id=session_id, user_id="web_user", stream=False)

    final_response = ""

    try:
        logger.info(f"Processing chat for session {session_id}: {request.message[:50]}...")
        
        async for msg, last in runner.query_handler(msgs=[user_msg], request=agent_request):
            if msg is not None and last:
                final_response = extract_final_text(msg)

        logger.info(f"Response received, length: {len(final_response)}")

        if not final_response.strip():
            final_response = "I apologize, I couldn't generate a response. Please try again."

    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        logger.error(f"Chat error: {e}\n{error_detail}")
        # Return the actual error for debugging
        final_response = f"Error: {str(e)}"

    return ChatResponse(response=final_response, session_id=session_id)

@router.post("/chat/stream")
async def chat_stream(request: ChatRequest, runner = Depends(get_runner)):
    """Stream a chat response."""
    from agentscope.message import Msg
    from agentscope_runtime.engine.schemas.agent_schemas import AgentRequest, Message, TextContent

    session_id = request.session_id or str(uuid.uuid4())
    user_msg = Msg(name="user", content=request.message, role="user")
    user_message = Message(role="user", type="message", content=[TextContent(text=request.message)])
    agent_request = AgentRequest(input=[user_message], session_id=session_id, user_id="web_user", stream=True)

    last_text = ""

    async def generate():
        nonlocal last_text
        try:
            async for msg, last in runner.query_handler(msgs=[user_msg], request=agent_request):
                if msg:
                    text = extract_final_text(msg)
                    if len(text) > len(last_text):
                        yield text[len(last_text):]
                        last_text = text
            yield f"\n\n---SESSION_ID:{session_id}---"
        except Exception as e:
            yield f"Error: {str(e)}"

    return StreamingResponse(generate(), media_type="text/plain", headers={"X-Session-ID": session_id})
