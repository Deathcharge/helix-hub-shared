#!/usr/bin/env python3
"""
Railway-compatible wrapper for WebSocket service.
Fixes relative import issues by setting up proper Python path.
"""

import os
import sys

# Add the current directory to Python path to resolve relative imports
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)  # Parent directory (project root)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import logging

# Now we can import the websocket_service module properly
from apps.backend.services.websocket_service import app

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    import uvicorn

    # Get port from Railway environment, default to 8001
    port = int(os.getenv("PORT", 8001))

    logger.info("🚀 Starting Helix WebSocket Service on port %s", port)
    logger.info("📁 Project root: %s", project_root)

    # Start the WebSocket application
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info", access_log=True)
