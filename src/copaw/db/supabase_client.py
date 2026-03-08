# -*- coding: utf-8 -*-
"""Supabase client for Mini Bee SaaS backend.

This module provides Supabase integration for:
- User authentication (JWT verification)
- Conversation storage
- Message history
- User memory persistence
"""

import os
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# Supabase configuration from environment variables
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

_supabase_client = None
_supabase_admin_client = None


def get_supabase_client():
    """Get Supabase client with anon key."""
    global _supabase_client
    
    if _supabase_client is None:
        if not SUPABASE_URL or not SUPABASE_ANON_KEY:
            logger.warning("Supabase credentials not configured.")
            return None
        
        try:
            from supabase import create_client
            _supabase_client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
            logger.info("Supabase client initialized")
        except ImportError:
            logger.error("supabase package not installed. Run: pip install supabase")
            return None
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
            return None
    
    return _supabase_client


def get_supabase_admin_client():
    """Get Supabase admin client with service role key."""
    global _supabase_admin_client
    
    if _supabase_admin_client is None:
        if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
            logger.warning("Supabase admin credentials not configured.")
            return None
        
        try:
            from supabase import create_client
            _supabase_admin_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
            logger.info("Supabase admin client initialized")
        except ImportError:
            logger.error("supabase package not installed")
            return None
        except Exception as e:
            logger.error(f"Failed to initialize Supabase admin client: {e}")
            return None
    
    return _supabase_admin_client


async def verify_jwt(token: str) -> Optional[Dict[str, Any]]:
    """Verify a Supabase JWT token and return user info."""
    import jwt
    
    if not token:
        return None
    
    if token.startswith("Bearer "):
        token = token[7:]
    
    try:
        jwt_secret = os.environ.get("SUPABASE_JWT_SECRET", SUPABASE_ANON_KEY)
        
        decoded = jwt.decode(
            token,
            jwt_secret,
            algorithms=["HS256"],
            audience="authenticated"
        )
        
        return {
            "user_id": decoded.get("sub"),
            "email": decoded.get("email"),
            "role": decoded.get("role"),
        }
        
    except jwt.ExpiredSignatureError:
        logger.warning("JWT token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT: {e}")
        return None
    except Exception as e:
        logger.error(f"JWT verification error: {e}")
        return None


class ConversationManager:
    """Manages conversations and messages in Supabase."""
    
    def __init__(self):
        self.client = get_supabase_admin_client()
    
    async def create_conversation(self, user_id: str, title: str = "New Chat") -> Optional[str]:
        if not self.client:
            return None
        
        try:
            result = self.client.table("conversations").insert({
                "user_id": user_id,
                "title": title,
            }).execute()
            
            if result.data:
                return result.data[0]["id"]
        except Exception as e:
            logger.error(f"Failed to create conversation: {e}")
        
        return None
    
    async def get_conversations(self, user_id: str) -> List[Dict[str, Any]]:
        if not self.client:
            return []
        
        try:
            result = self.client.table("conversations").select("*").eq("user_id", user_id).order("updated_at", desc=True).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Failed to get conversations: {e}")
            return []
    
    async def get_conversation(self, conversation_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        if not self.client:
            return None
        
        try:
            conv_result = self.client.table("conversations").select("*").eq("id", conversation_id).eq("user_id", user_id).execute()
            
            if not conv_result.data:
                return None
            
            conversation = conv_result.data[0]
            
            msg_result = self.client.table("messages").select("*").eq("conversation_id", conversation_id).order("created_at").execute()
            conversation["messages"] = msg_result.data or []
            
            return conversation
        except Exception as e:
            logger.error(f"Failed to get conversation: {e}")
            return None
    
    async def add_message(self, conversation_id: str, role: str, content: str) -> bool:
        if not self.client:
            return False
        
        try:
            self.client.table("messages").insert({
                "conversation_id": conversation_id,
                "role": role,
                "content": content,
            }).execute()
            
            self.client.table("conversations").update({"updated_at": "now()"}).eq("id", conversation_id).execute()
            
            return True
        except Exception as e:
            logger.error(f"Failed to add message: {e}")
            return False
    
    async def delete_conversation(self, conversation_id: str, user_id: str) -> bool:
        if not self.client:
            return False
        
        try:
            result = self.client.table("conversations").delete().eq("id", conversation_id).eq("user_id", user_id).execute()
            return len(result.data) > 0
        except Exception as e:
            logger.error(f"Failed to delete conversation: {e}")
            return False


class MemoryManager:
    """Manages user memory in Supabase."""
    
    def __init__(self):
        self.client = get_supabase_admin_client()
    
    async def save_memory(self, user_id: str, key: str, value: str) -> bool:
        if not self.client:
            return False
        
        try:
            self.client.table("user_memory").upsert({
                "user_id": user_id,
                "key": key,
                "value": value,
            }, on_conflict="user_id,key").execute()
            return True
        except Exception as e:
            logger.error(f"Failed to save memory: {e}")
            return False
    
    async def get_memories(self, user_id: str) -> List[Dict[str, Any]]:
        if not self.client:
            return []
        
        try:
            result = self.client.table("user_memory").select("key,value,created_at").eq("user_id", user_id).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Failed to get memories: {e}")
            return []


# Singleton instances
_conversation_manager = None
_memory_manager = None


def get_conversation_manager() -> ConversationManager:
    global _conversation_manager
    if _conversation_manager is None:
        _conversation_manager = ConversationManager()
    return _conversation_manager


def get_memory_manager() -> MemoryManager:
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager()
    return _memory_manager
