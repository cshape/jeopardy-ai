import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles  # Add import for StaticFiles
from fastapi.middleware.cors import CORSMiddleware  # Add import for CORS middleware
from typing import Dict, Any, List, Optional
import json
import asyncio
import logging
from pathlib import Path
import subprocess  # Add this import for running the standalone AI player
from fastapi.responses import FileResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from .utils.file_loader import BoardFactory
from .models.board import Board
from .websockets.connection_manager import ConnectionManager
from .services.game_service import GameService
from .services.chat_manager import ChatManager  # Add import for ChatManager

# Try to import routers
try:
    from .routes import admin_routes
    has_admin_routes = True
except ImportError:
    has_admin_routes = False
    logger.warning("Admin routes not found, skipping")

try:
    from .routes import board_routes
    has_board_routes = True
except ImportError:
    has_board_routes = False
    logger.warning("Board routes not found, skipping")

app = FastAPI(title="Jeopardy Game")

# Update the CORS middleware settings to allow your ngrok domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Keep as is or specify your ngrok domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create static directory if it doesn't exist
static_dir = Path("static")
static_dir.mkdir(exist_ok=True)
static_audio_dir = static_dir / "audio"
static_audio_dir.mkdir(exist_ok=True)

# Mount static files directory for existing static content
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")

# Initialize connection manager and game service
connection_manager = ConnectionManager()
game_service = GameService(connection_manager)
chat_manager = ChatManager(connection_manager)  # Initialize chat manager
board_factory = BoardFactory()
board = board_factory.initialize()

# Store in app state for access in routes
app.state.connection_manager = connection_manager
app.state.game_service = game_service
app.state.chat_manager = chat_manager

# WebSocket route - define this BEFORE mounting static files at /
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    logger.debug("New WebSocket connection request")
    try:
        client_id = await connection_manager.connect(websocket)
        await game_service.send_game_state(websocket)
        # Send chat history to new connection
        await chat_manager.send_chat_history(websocket)
        
        while True:
            try:
                message = await websocket.receive_text()
                data = json.loads(message)
                logger.debug(f"Received WebSocket message from {client_id}: {data}")
                
                topic = data.get('topic')
                payload = data.get('payload', {})
                
                if topic == 'com.sc2ctl.jeopardy.register_player':
                    name = payload.get('name')
                    preferences = payload.get('preferences', '')
                    logger.info(f"Registering player: {name} with preferences: {preferences}")
                    success = await game_service.register_player(websocket, name, preferences)
                    if success:
                        await game_service.connection_manager.send_personal_message(
                            websocket,
                            "com.sc2ctl.jeopardy.register_player_response",
                            {"success": True, "name": name}
                        )
                
                elif topic == 'com.sc2ctl.jeopardy.select_board':
                    # Check for both camelCase and snake_case versions to be robust
                    board_id = payload.get('boardId') or payload.get('board_id')
                    logger.info(f"Selecting board: {board_id}")
                    await game_service.select_board(board_id)
                
                elif topic == game_service.QUESTION_DISPLAY_TOPIC:
                    category = payload.get('category')
                    value = payload.get('value')
                    logger.info(f"Displaying question: {category} - ${value}")
                    await game_service.display_question(category, value)
                    await game_service.change_buzzer_status(True)
                
                elif topic == 'com.sc2ctl.jeopardy.daily_double':
                    category = payload.get('category')
                    value = payload.get('value')
                    logger.info(f"Daily double selected: {category} - ${value}")
                    await game_service.display_question(category, value)
                
                elif topic == game_service.BUZZER_TOPIC:
                    timestamp = payload.get('timestamp')
                    await game_service.handle_buzz(websocket, timestamp)
                
                elif topic == game_service.QUESTION_ANSWER_TOPIC:
                    correct = payload.get('correct')
                    contestant = payload.get('contestant')
                    logger.info(f"Answering question: {'correct' if correct else 'incorrect'}")
                    await game_service.answer_question(correct, contestant)
                
                elif topic == game_service.QUESTION_DISMISS_TOPIC:
                    await game_service.dismiss_question()
                
                elif topic == game_service.BOARD_INIT_TOPIC:
                    await game_service.send_categories()
                
                elif topic == game_service.DAILY_DOUBLE_BET_TOPIC:
                    contestant = payload.get('contestant')
                    bet = payload.get('bet')
                    logger.info(f"Daily double bet from {contestant}: ${bet}")
                    await game_service.handle_daily_double_bet(contestant, bet)
                
                elif topic == 'com.sc2ctl.jeopardy.chat_message':
                    username = payload.get('username', 'Anonymous')
                    message_text = payload.get('message', '')
                    
                    # Broadcast the chat message to all clients
                    await chat_manager.handle_message(username, message_text)
                    
                    # Forward to game service for AI host processing
                    await game_service.handle_chat_message(username, message_text)

                elif topic == 'com.sc2ctl.jeopardy.audio_complete':
                    # Handle audio completion notification from frontend
                    audio_id = payload.get('audio_id')
                    if audio_id:
                        logger.info(f"Received audio completion via WebSocket: {audio_id}")
                        await game_service.handle_audio_completed(audio_id)
                    else:
                        logger.warning("Received audio completion message without audio_id")

                elif topic == 'com.sc2ctl.jeopardy.start_ai_game':
                    logger.info("Starting AI game...")
                    # Launch the standalone AI player script as a separate process
                    num_players = payload.get("num_players", 3)
                    headless = payload.get("headless", True)
                    
                    try:
                        # Get the project root directory
                        project_root = Path(__file__).parent.parent
                        standalone_script = project_root / "standalone_ai_player.py"
                        
                        # Make sure the script is executable
                        os.chmod(standalone_script, 0o755)
                        
                        # Launch the script as a separate process
                        headless_arg = "true" if headless else "false"
                        cmd = [str(standalone_script), str(num_players), headless_arg]
                        
                        logger.info(f"Launching standalone AI player with: {' '.join(cmd)}")
                        process = subprocess.Popen(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            cwd=str(project_root)
                        )
                        
                        # Note: We're deliberately NOT waiting for the process to complete
                        # since it will run indefinitely until stopped
                        
                        await connection_manager.send_personal_message(
                            websocket,
                            "com.sc2ctl.jeopardy.ai_game_started",
                            {"status": "success"}
                        )
                        logger.info("AI game started successfully")
                    except Exception as e:
                        logger.error(f"Failed to start standalone AI player: {e}")
                        await connection_manager.send_personal_message(
                            websocket,
                            "com.sc2ctl.jeopardy.ai_game_started",
                            {"status": "error", "message": f"Failed to start AI game: {str(e)}"}
                        )
                
                elif topic == 'com.sc2ctl.jeopardy.stop_ai_game':
                    logger.info("Stopping AI game...")
                    try:
                        # Find and kill the standalone AI player process
                        if os.name == 'posix':  # macOS, Linux
                            subprocess.run(["pkill", "-f", "standalone_ai_player.py"], check=False)
                        else:  # Windows
                            subprocess.run(["taskkill", "/f", "/im", "python.exe"], check=False)
                            
                        await connection_manager.send_personal_message(
                            websocket,
                            "com.sc2ctl.jeopardy.ai_game_stopped",
                            {"status": "success"}
                        )
                        logger.info("AI game stopped successfully")
                    except Exception as e:
                        logger.error(f"Failed to stop AI game: {e}")
                        await connection_manager.send_personal_message(
                            websocket,
                            "com.sc2ctl.jeopardy.ai_game_stopped",
                            {"status": "error", "message": f"Failed to stop AI game: {str(e)}"}
                        )
                
                elif topic == 'com.sc2ctl.jeopardy.start_ai_host':
                    logger.info("Starting AI host...")
                    headless = payload.get("headless", True)
                    
                    try:
                        # AI host is now integrated directly in the game service
                        # No need to start a separate process
                        await connection_manager.send_personal_message(
                            websocket,
                            "com.sc2ctl.jeopardy.ai_host_started",
                            {"status": "success"}
                        )
                        logger.info("AI host started successfully")
                    except Exception as e:
                        logger.error(f"Failed to start AI host: {e}")
                        await connection_manager.send_personal_message(
                            websocket,
                            "com.sc2ctl.jeopardy.ai_host_started",
                            {"status": "error", "message": f"Failed to start AI host: {str(e)}"}
                        )
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode WebSocket message: {e}")
                continue
                
    except WebSocketDisconnect:
        await connection_manager.disconnect(websocket)
        logger.info(f"Client disconnected")
    except Exception as e:
        logger.error(f"Error in WebSocket connection: {e}")
        await connection_manager.disconnect(websocket)

# Routes for web pages - Define all HTTP routes before mounting static files
@app.get("/")
async def index():
    return FileResponse("frontend/dist/index.html")

@app.get("/admin")
async def admin():
    return FileResponse("frontend/dist/index.html")

@app.get("/board")
async def view_board():
    return FileResponse("frontend/dist/index.html")

@app.get("/play/{username}")
async def play(username: str):
    return FileResponse("frontend/dist/index.html")

@app.get("/contestants")
async def contestants():
    return FileResponse("frontend/dist/index.html")

@app.get("/api/boards")
async def get_available_boards():
    """Get list of available board files from game_data directory"""
    boards_dir = Path("game_data")
    if not boards_dir.exists():
        # Also check in app/game_data
        boards_dir = Path("app/game_data")
    
    if boards_dir.exists():
        # Get all .json files and remove extension
        board_files = [f.stem for f in boards_dir.glob("*.json")]
        return {"boards": board_files}
    
    return {"boards": []}

@app.post("/api/load-board")
async def load_board(board_request: dict):
    board_name = board_request.get("board")
    if not board_name:
        raise HTTPException(status_code=400, detail="Board name is required")
    
    try:
        # Load the new board using the factory
        new_board = board_factory.load_board(board_name)
        
        # Update game service with new board
        game_service.board = new_board
        
        # Broadcast new board to all clients
        await game_service.send_categories()
        
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error loading board: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# New API endpoint for playing audio
@app.post("/api/play-audio")
async def play_audio(request: dict):
    """
    API endpoint that allows the AI Host to request audio playback on all clients.
    
    Request body should contain:
    {
        "audio_url": "/audio/filename.wav"  # Path to the audio file on the server
    }
    """
    audio_url = request.get("audio_url")
    if not audio_url:
        raise HTTPException(status_code=400, detail="audio_url is required")
    
    logger.info(f"Broadcasting audio playback request: {audio_url}")
    
    # Broadcast to all clients
    await connection_manager.broadcast_message(
        "com.sc2ctl.jeopardy.play_audio",
        {"url": audio_url}
    )
    
    return {"status": "success", "message": "Audio broadcast initiated"}

# Include routers
if has_admin_routes:
    app.include_router(admin_routes.router)
if has_board_routes:
    app.include_router(board_routes.router)

# Add favicon route to prevent 404 errors
@app.get("/favicon.ico")
async def favicon():
    return FileResponse("frontend/dist/favicon.ico", media_type="image/x-icon")

# Startup event
@app.on_event("startup")
async def startup_event():
    # Initialize the game service and start the AI host
    logger.info("Starting application...")
    await game_service.startup()
    logger.info("Application startup completed")

# Mount frontend static assets AFTER all API and WebSocket routes are defined
app.mount("/assets", StaticFiles(directory="frontend/dist/assets"), name="assets")

# This should be the LAST mount
app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="frontend")

# Run with: uvicorn app.main:app --reload
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True) 