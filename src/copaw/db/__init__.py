# -*- coding: utf-8 -*-
"""Database module for Mini Bee SaaS."""

from .supabase_client import get_supabase_client, get_supabase_admin_client

__all__ = ["get_supabase_client", "get_supabase_admin_client"]
