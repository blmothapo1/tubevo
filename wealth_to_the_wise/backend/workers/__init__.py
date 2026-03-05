# filepath: backend/workers/__init__.py
"""
Empire OS background workers.

Each worker module provides an ``async def <name>_loop()`` coroutine
that is started by ``app.py`` behind the appropriate feature flag.
"""
