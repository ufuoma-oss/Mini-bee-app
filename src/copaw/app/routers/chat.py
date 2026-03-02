# -*- coding: utf-8 -*-
"""Simple Chat API for SaaS frontend - Direct model chat without agent tools."""

import uuid
import os
import logging
from typing import Optional

from fastapi import APIRouter
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


# Simple in-memory conversation history (for demo purposes)
# In production, use a proper database
_conversations = {}


def get_model_config():
    """Get model configuration from environment variables."""
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    model = os.getenv("OPENROUTER_MODEL", "openrouter/free")

    if api_key:
        return {
            "api_key": api_key,
            "model": model,
            "base_url": "https://openrouter.ai/api/v1"
        }

    # Fallback to DashScope
    return {
        "api_key": os.getenv("DASHSCOPE_API_KEY", ""),
        "model": "qwen3-max",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"
    }


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Send a message and get an AI response.

    This is a simple chat endpoint for the SaaS frontend.
    """
    import httpx

    session_id = request.session_id or str(uuid.uuid4())
    config = get_model_config()

    # Get conversation history
    history = _conversations.get(session_id, [])
    history.append({"role": "user", "content": request.message})

    # Keep only last 10 messages for context
    if len(history) > 10:
        history = history[-10:]

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{config['base_url']}/chat/completions",
                headers={
                    "Authorization": f"Bearer {config['api_key']}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://mini-bee.vercel.app",
                    "X-Title": "Mini Bee"
                },
                json={
                    "model": config["model"],
                    "messages": history,
                    "max_tokens": 1000
                }
            )

            if response.status_code == 200:
                data = response.json()
                assistant_message = data["choices"][0]["message"]["content"]

                # Update history with assistant response
                history.append({"role": "assistant", "content": assistant_message})
                _conversations[session_id] = history

                return ChatResponse(
                    response=assistant_message,
                    session_id=session_id
                )
            else:
                error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {"error": response.text}
                logger.error(f"API error: {response.status_code} - {error_data}")
                return ChatResponse(
                    response=f"I encountered an error (code: {response.status_code}). Please try again.",
                    session_id=session_id
                )

    except httpx.TimeoutException:
        logger.error("Request timed out")
        return ChatResponse(
            response="The request timed out. Please try again.",
            session_id=session_id
        )
    except Exception as e:
        logger.error(f"Chat error: {e}")
        return ChatResponse(
            response=f"I encountered an error: {str(e)}. Please try again.",
            session_id=session_id
        )


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Stream a chat response.

    Returns the response as a stream of text chunks.
    """
    from fastapi.responses import StreamingResponse
    import httpx

    session_id = request.session_id or str(uuid.uuid4())
    config = get_model_config()

    history = _conversations.get(session_id, [])
    history.append({"role": "user", "content": request.message})

    if len(history) > 10:
        history = history[-10:]

    async def generate():
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{config['base_url']}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {config['api_key']}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://mini-bee.vercel.app",
                        "X-Title": "Mini Bee"
                    },
                    json={
                        "model": config["model"],
                        "messages": history,
                        "max_tokens": 1000,
                        "stream": True
                    }
                ) as response:
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data = line[6:]
                            if data == "[DONE]":
                                break
                            try:
                                import json
                                chunk = json.loads(data)
                                if chunk.get("choices") and chunk["choices"][0].get("delta", {}).get("content"):
                                    yield chunk["choices"][0]["delta"]["content"]
                            except json.JSONDecodeError:
                                continue

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
