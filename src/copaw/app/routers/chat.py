# -*- coding: utf-8 -*-
"""Chat API for SaaS frontend - Full agent with tools + Supabase integration."""

import uuid
import logging
import re
from typing import Optional, List

from fastapi import APIRouter, Depends, Request, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., description="User message")
    session_id: Optional[str] = Field(None, description="Session ID (conversation ID)")
    context: Optional[dict] = Field(None, description="Optional context")


class ChatResponse(BaseModel):
    response: str = Field(..., description="AI response")
    session_id: str = Field(..., description="Session ID")


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: str


class ConversationResponse(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    messages: Optional[List[MessageResponse]] = None


def get_runner(request: Request):
    runner = getattr(request.app.state, "runner", None)
    if runner is None:
        raise HTTPException(status_code=503, detail="Runner not initialized")
    return runner


def extract_final_text(msg) -> str:
    if msg is None:
        return ""
    msg_str = str(msg)
    pattern = r"'text':\s*'(.*?)(?='\s*[,}]|\s*$)"
    matches = re.findall(pattern, msg_str, re.DOTALL)
    if matches:
        text = matches[-1]
        return text.replace("\n", "\n").replace("\'", "'").replace('\"', '"').replace("\\", "\\")
    return ""


async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """Verify JWT and return user info. Falls back to anonymous user if no auth."""
    from copaw.db.supabase_client import verify_jwt
    
    if not authorization:
        return {"user_id": "anonymous", "email": None, "role": "anon"}
    
    user = await verify_jwt(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return user


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    runner = Depends(get_runner),
    user: dict = Depends(get_current_user)
):
    """Send a message and get an AI response."""
    from agentscope.message import Msg
    from agentscope_runtime.engine.schemas.agent_schemas import AgentRequest, Message, TextContent
    from copaw.db.supabase_client import get_conversation_manager
    
    user_id = user.get("user_id", "anonymous")
    session_id = request.session_id or str(uuid.uuid4())
    
    conv_manager = get_conversation_manager()
    if request.session_id:
        await conv_manager.add_message(session_id, "user", request.message)
    
    user_msg = Msg(name="user", content=request.message, role="user")
    user_message = Message(role="user", type="message", content=[TextContent(text=request.message)])
    agent_request = AgentRequest(
        input=[user_message],
        session_id=session_id,
        user_id=user_id,
        stream=False
    )

    final_response = ""

    try:
        logger.info(f"Processing chat for user {user_id}, session {session_id}")
        
        async for msg, last in runner.query_handler(msgs=[user_msg], request=agent_request):
            if msg is not None and last:
                final_response = extract_final_text(msg)

        if not final_response.strip():
            final_response = "I apologize, I couldn't generate a response. Please try again."

        if request.session_id:
            await conv_manager.add_message(session_id, "assistant", final_response)

    except Exception as e:
        import traceback
        logger.error(f"Chat error: {e}\n{traceback.format_exc()}")
        final_response = f"Error: {str(e)}"

    return ChatResponse(response=final_response, session_id=session_id)


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    runner = Depends(get_runner),
    user: dict = Depends(get_current_user)
):
    """Stream a chat response."""
    from agentscope.message import Msg
    from agentscope_runtime.engine.schemas.agent_schemas import AgentRequest, Message, TextContent
    from copaw.db.supabase_client import get_conversation_manager
    
    user_id = user.get("user_id", "anonymous")
    session_id = request.session_id or str(uuid.uuid4())
    
    conv_manager = get_conversation_manager()
    if request.session_id:
        await conv_manager.add_message(session_id, "user", request.message)
    
    user_msg = Msg(name="user", content=request.message, role="user")
    user_message = Message(role="user", type="message", content=[TextContent(text=request.message)])
    agent_request = AgentRequest(
        input=[user_message],
        session_id=session_id,
        user_id=user_id,
        stream=True
    )

    last_text = ""
    full_response = ""

    async def generate():
        nonlocal last_text, full_response
        try:
            async for msg, last in runner.query_handler(msgs=[user_msg], request=agent_request):
                if msg:
                    text = extract_final_text(msg)
                    if len(text) > len(last_text):
                        chunk = text[len(last_text):]
                        full_response = text
                        last_text = text
                        yield chunk
            yield f"\n\n---SESSION_ID:{session_id}---"
            
            if request.session_id and full_response:
                await conv_manager.add_message(session_id, "assistant", full_response)
                
        except Exception as e:
            yield f"Error: {str(e)}"

    return StreamingResponse(
        generate(),
        media_type="text/plain",
        headers={"X-Session-ID": session_id}
    )


# ============ Conversation Management Endpoints ============

@router.get("/conversations", response_model=List[ConversationResponse])
async def list_conversations(user: dict = Depends(get_current_user)):
    """List all conversations for the current user."""
    from copaw.db.supabase_client import get_conversation_manager
    
    user_id = user.get("user_id", "anonymous")
    if user_id == "anonymous":
        return []
    
    conv_manager = get_conversation_manager()
    conversations = await conv_manager.get_conversations(user_id)
    
    return [
        ConversationResponse(
            id=conv["id"],
            title=conv["title"] or "Untitled",
            created_at=conv["created_at"],
            updated_at=conv["updated_at"]
        )
        for conv in conversations
    ]


@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(
    user: dict = Depends(get_current_user),
    title: str = "New Chat"
):
    """Create a new conversation."""
    from copaw.db.supabase_client import get_conversation_manager
    
    user_id = user.get("user_id", "anonymous")
    if user_id == "anonymous":
        raise HTTPException(status_code=401, detail="Authentication required")
    
    conv_manager = get_conversation_manager()
    conv_id = await conv_manager.create_conversation(user_id, title)
    
    if not conv_id:
        raise HTTPException(status_code=500, detail="Failed to create conversation")
    
    return ConversationResponse(
        id=conv_id,
        title=title,
        created_at="",
        updated_at=""
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: str,
    user: dict = Depends(get_current_user)
):
    """Get a conversation with all messages."""
    from copaw.db.supabase_client import get_conversation_manager
    
    user_id = user.get("user_id", "anonymous")
    if user_id == "anonymous":
        raise HTTPException(status_code=401, detail="Authentication required")
    
    conv_manager = get_conversation_manager()
    conversation = await conv_manager.get_conversation(conversation_id, user_id)
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return ConversationResponse(
        id=conversation["id"],
        title=conversation["title"] or "Untitled",
        created_at=conversation["created_at"],
        updated_at=conversation["updated_at"],
        messages=[
            MessageResponse(
                id=msg["id"],
                role=msg["role"],
                content=msg["content"],
                created_at=msg["created_at"]
            )
            for msg in conversation.get("messages", [])
        ]
    )


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user: dict = Depends(get_current_user)
):
    """Delete a conversation."""
    from copaw.db.supabase_client import get_conversation_manager
    
    user_id = user.get("user_id", "anonymous")
    if user_id == "anonymous":
        raise HTTPException(status_code=401, detail="Authentication required")
    
    conv_manager = get_conversation_manager()
    success = await conv_manager.delete_conversation(conversation_id, user_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return {"status": "deleted"}


# ============ Memory Endpoints ============

@router.get("/memory")
async def get_memory(user: dict = Depends(get_current_user)):
    """Get all memory items for the current user."""
    from copaw.db.supabase_client import get_memory_manager
    
    user_id = user.get("user_id", "anonymous")
    if user_id == "anonymous":
        return {"memories": []}
    
    memory_manager = get_memory_manager()
    memories = await memory_manager.get_memories(user_id)
    
    return {"memories": memories}


@router.post("/memory")
async def save_memory(
    key: str,
    value: str,
    user: dict = Depends(get_current_user)
):
    """Save a memory item."""
    from copaw.db.supabase_client import get_memory_manager
    
    user_id = user.get("user_id", "anonymous")
    if user_id == "anonymous":
        raise HTTPException(status_code=401, detail="Authentication required")
    
    memory_manager = get_memory_manager()
    success = await memory_manager.save_memory(user_id, key, value)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save memory")
    
    return {"status": "saved"}


# ============ Auth Verification Endpoint ============

@router.get("/auth/verify")
async def verify_auth(user: dict = Depends(get_current_user)):
    """Verify authentication and return user info."""
    return {
        "user_id": user.get("user_id"),
        "email": user.get("email"),
        "role": user.get("role", "user")
    }
