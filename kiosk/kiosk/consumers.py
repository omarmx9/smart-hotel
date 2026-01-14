"""
WebSocket consumers for kiosk app.
Provides real-time video streaming proxy to MRZ backend.
"""
import json
import asyncio
import logging
import os
import websockets
from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)

# MRZ backend WebSocket URL
MRZ_SERVICE_URL = os.environ.get('MRZ_SERVICE_URL', 'http://mrz-backend:5000')
MRZ_WS_URL = MRZ_SERVICE_URL.replace('http://', 'ws://').replace('https://', 'wss://') + '/api/stream/ws'


class MRZStreamConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer that proxies video frames to MRZ backend.
    
    Protocol:
    1. Client connects and sends {"action": "init"}
    2. Client sends binary frames (JPEG/WebP)
    3. Server forwards to Flask backend and returns detection results
    4. Client sends {"action": "capture"} to capture best frame
    5. Client sends {"action": "close"} to end session
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.backend_ws = None
        self.backend_task = None
        self.session_id = None
        self.connected = False
        self.frame_count = 0
    
    async def connect(self):
        """Accept WebSocket connection and connect to backend."""
        await self.accept()
        self.connected = True
        logger.info("[MRZStream] Client connected")
        
        try:
            # Connect to Flask backend WebSocket
            self.backend_ws = await websockets.connect(
                MRZ_WS_URL,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5,
            )
            logger.info(f"[MRZStream] Connected to backend: {MRZ_WS_URL}")
            
            # Start background task to receive from backend
            self.backend_task = asyncio.create_task(self.receive_from_backend())
            
        except Exception as e:
            logger.error(f"[MRZStream] Backend connection failed: {e}")
            await self.send(text_data=json.dumps({
                "error": f"Backend connection failed: {e}",
                "detected": False
            }))
    
    async def disconnect(self, close_code):
        """Clean up on disconnect."""
        self.connected = False
        logger.info(f"[MRZStream] Client disconnected (code: {close_code}), processed {self.frame_count} frames")
        
        # Cancel backend receiver task
        if self.backend_task:
            self.backend_task.cancel()
            try:
                await self.backend_task
            except asyncio.CancelledError:
                pass
        
        # Close backend connection
        if self.backend_ws:
            try:
                await self.backend_ws.close()
            except:
                pass
    
    async def receive(self, text_data=None, bytes_data=None):
        """
        Receive message from client (browser).
        Forward to Flask backend.
        """
        if not self.backend_ws:
            await self.send(text_data=json.dumps({
                "error": "Backend not connected",
                "detected": False
            }))
            return
        
        try:
            if bytes_data:
                # Binary frame - forward directly to backend
                self.frame_count += 1
                await self.backend_ws.send(bytes_data)
                
            elif text_data:
                # JSON command - forward to backend
                await self.backend_ws.send(text_data)
                
                # Track session ID from init response
                try:
                    data = json.loads(text_data)
                    if data.get('action') == 'init':
                        logger.info("[MRZStream] Session init requested")
                except:
                    pass
                    
        except websockets.exceptions.ConnectionClosed:
            logger.warning("[MRZStream] Backend connection closed")
            await self.send(text_data=json.dumps({
                "error": "Backend connection lost",
                "detected": False
            }))
        except Exception as e:
            logger.error(f"[MRZStream] Send error: {e}")
            await self.send(text_data=json.dumps({
                "error": str(e),
                "detected": False
            }))
    
    async def receive_from_backend(self):
        """
        Background task to receive messages from Flask backend.
        Forward all responses to client.
        """
        try:
            async for message in self.backend_ws:
                if not self.connected:
                    break
                    
                # Forward response to client
                if isinstance(message, bytes):
                    await self.send(bytes_data=message)
                else:
                    await self.send(text_data=message)
                    
                    # Track session ID
                    try:
                        data = json.loads(message)
                        if data.get('action') == 'init_ok':
                            self.session_id = data.get('session_id')
                            logger.info(f"[MRZStream] Session initialized: {self.session_id}")
                    except:
                        pass
                        
        except websockets.exceptions.ConnectionClosed:
            logger.info("[MRZStream] Backend connection closed")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[MRZStream] Backend receive error: {e}")
