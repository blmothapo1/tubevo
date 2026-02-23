# filepath: backend/rate_limit.py
"""
Rate-limiting setup using SlowAPI.

SlowAPI wraps the proven ``limits`` library and plugs into FastAPI/Starlette.
Limits can be per-IP by default, and later per-user-ID once auth (Item 2) lands.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

# Default key function: rate-limit by client IP.
# Item 2 will add a `get_current_user_id` key-func for authenticated routes.
limiter = Limiter(key_func=get_remote_address)
