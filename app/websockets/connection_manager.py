import logging, json
from typing import List, Dict
from fastapi import WebSocket, WebSocketDisconnect
import uuid

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.admin_connections: List[WebSocket] = []
        self.player_connections: List[WebSocket] = []
        self.topic_subscriptions: Dict[str, List[WebSocket]] = {}  # New dictionary for topic subscriptions

    async def connect(self, websocket: WebSocket) -> str:
        """Connect a websocket and return its client_id"""
        await websocket.accept()
        client_id = str(uuid.uuid4())
        self.active_connections[client_id] = websocket
        return client_id

    async def disconnect(self, websocket: WebSocket) -> None:
        """Disconnect a websocket"""
        # Find and remove the websocket from active connections
        to_remove = None
        for client_id, conn in self.active_connections.items():
            if conn == websocket:
                to_remove = client_id
                break
                
        if to_remove:
            del self.active_connections[to_remove]

    async def send_personal_message(self, websocket: WebSocket, topic: str, payload: dict):
        """Send a message to a specific client"""
        message = {"topic": topic, "payload": payload}
        await websocket.send_json(message)

    async def broadcast_message(self, topic: str, payload: dict):
        """Broadcast a message to all connected clients"""
        message = {"topic": topic, "payload": payload}
        disconnected = []
        
        for client_id, connection in self.active_connections.items():
            try:
                await connection.send_json(message)
            except:
                disconnected.append(client_id)
                
        # Clean up disconnected clients
        for client_id in disconnected:
            self.disconnect(connection)

    async def broadcast_to_topic(self, topic: str, message: dict):
        if topic not in self.topic_subscriptions:
            return
            
        message_json = json.dumps(message)
        subscribers = self.topic_subscriptions[topic].copy()
        
        for websocket in subscribers:
            try:
                await websocket.send_text(message_json)
            except Exception as e:
                logger.error(f"Failed to send to subscriber {id(websocket)}: {e}")
                await self.disconnect(websocket)
    
    async def broadcast(self, data: dict):
        json_data = json.dumps(data)
        for connection in self.active_connections.values():
            try:
                await connection.send_text(json_data)
            except Exception:
                # Handle disconnections or errors
                await self.disconnect(connection)

    async def handle_message(self, websocket: WebSocket, message_data: str):
        """Handle incoming WebSocket message and route to appropriate handler"""
        try:
            message = json.loads(message_data)
            
            # Get the topic and payload from the message
            topic = message.get("topic")
            payload = message.get("payload", {})
            
            logging.info(f"Received message on topic: {topic}")
            
            # Handle based on topic
            if topic == "com.sc2ctl.jeopardy.buzzer":
                await self.handle_buzzer(websocket, payload)
            elif topic == "com.sc2ctl.jeopardy.chat":
                await self.handle_chat(websocket, payload)
            elif topic == "com.sc2ctl.jeopardy.register":
                await self.handle_registration(websocket, payload)
            elif topic == "com.sc2ctl.jeopardy.select_board":
                await self.handle_board_selection(websocket, payload)
            elif topic == "com.sc2ctl.jeopardy.select_question":
                await self.handle_question_selection(websocket, payload)
            elif topic == "com.sc2ctl.jeopardy.audio_complete":
                await self.handle_audio_complete(websocket, payload)
            else:
                logging.warning(f"Unhandled message topic: {topic}")
        except json.JSONDecodeError:
            logging.error(f"Invalid message format: {message_data}")
        except Exception as e:
            logging.error(f"Error handling message: {e}")
            
    async def handle_audio_complete(self, websocket: WebSocket, payload: Dict):
        """Handle audio completion notifications from clients"""
        try:
            audio_id = payload.get("audio_id")
            if not audio_id:
                logging.warning("Audio completion message missing audio_id")
                return
                
            logging.info(f"🔊 WebSocket audio completion for: {audio_id}")
            
            # Get the game service from the application state
            if hasattr(websocket.app, "state") and hasattr(websocket.app.state, "game_service"):
                game_service = websocket.app.state.game_service
                
                # Mark the audio as completed
                game_service.mark_audio_completed(audio_id)
                
                # Forward the completion message to all clients
                await self.broadcast_message(
                    "com.sc2ctl.jeopardy.audio_complete",
                    {"audio_id": audio_id}
                )
            else:
                logging.error("Game service not available in application state")
        except Exception as e:
            logging.error(f"Error handling audio completion: {e}") 