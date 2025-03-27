"""
AI Host Service for Jeopardy

This module implements an AI host that interacts with the Jeopardy game
directly through the backend, eliminating the need for Selenium.
"""

import logging
import asyncio
import time
import os
from typing import Optional

from .audio_manager import AudioManager
from .game_state_manager import GameStateManager
from .answer_evaluator import AnswerEvaluator
from .board_manager import BoardManager
from .clue_processor import ClueProcessor
from .chat_processor import ChatProcessor
from .buzzer_manager import BuzzerManager
from .game_flow_manager import GameFlowManager
from .utils.helpers import is_same_player, cleanup_audio_files

logger = logging.getLogger(__name__)

class AIHostService:
    """
    AI host service that directly interacts with the Jeopardy game backend.
    
    This host monitors player interactions, evaluates answers using LLM,
    and manages the game flow without using browser automation.
    """
    
    def __init__(self, name: str):
        """
        Initialize the AI host service.
        
        Args:
            name: The name of the AI host
        """
        logger.info(f"Initializing AI Host Service with name: {name}")
        self.name = name
        
        # Initialize API keys
        self.inworld_api_key = os.environ.get("INWORLD_API_KEY")
        self.tts_voice = "Timothy"
        
        # Initialize component managers
        self.game_state_manager = GameStateManager()
        self.audio_manager = AudioManager(api_key=self.inworld_api_key, voice=self.tts_voice)
        self.answer_evaluator = AnswerEvaluator()
        self.board_manager = BoardManager()
        self.clue_processor = ClueProcessor()
        self.chat_processor = ChatProcessor()
        self.buzzer_manager = BuzzerManager()
        self.game_flow_manager = GameFlowManager()
        
        # Set up the chat processor
        self.chat_processor.set_host_name(name)
        
        # WebSocket connection manager reference (to be set from outside)
        self.websocket_manager = None
        
        # Game service reference (to be set from outside)
        self.game_service = None
        
    async def start(self) -> bool:
        """Start the AI host service."""
        try:
            logger.info(f"Starting AI Host Service with name '{self.name}'")
            
            # Start the audio queue processor
            await self.audio_manager.start()
            
            return True
            
        except Exception as e:
            logger.error(f"Error starting AI host service: {e}")
            self.shutdown()
            return False
    
    def shutdown(self):
        """Shut down the AI host service and clean up resources."""
        try:
            # Shut down audio manager
            self.audio_manager.shutdown()
                
            logger.info("AI host service shut down")
        except Exception as e:
            logger.error(f"Error shutting down AI host service: {e}")
    
    def set_websocket_manager(self, websocket_manager):
        """Set the WebSocket manager for communication with frontend clients."""
        self.websocket_manager = websocket_manager
        logger.info("WebSocket manager set for AI Host Service")
    
    def set_game_service(self, game_service):
        """Set the game service for direct interaction with game state."""
        self.game_service = game_service
        
        # Propagate the game service to all components that need it
        self.audio_manager.set_game_service(game_service)
        self.board_manager.set_game_service(game_service)
        self.clue_processor.set_game_service(game_service)
        
        # Set up chat processor dependencies
        self.chat_processor.set_dependencies(
            game_service=game_service,
            game_state_manager=self.game_state_manager,
            clue_processor=self.clue_processor,
            answer_evaluator=self.answer_evaluator
        )
        
        # Set up buzzer manager dependencies
        self.buzzer_manager.set_dependencies(
            game_service=game_service,
            game_state_manager=self.game_state_manager,
            chat_processor=self.chat_processor,
            audio_manager=self.audio_manager
        )
        
        # Set up game flow manager dependencies
        self.game_flow_manager.set_dependencies(
            game_service=game_service,
            game_state_manager=self.game_state_manager,
            chat_processor=self.chat_processor,
            audio_manager=self.audio_manager,
            buzzer_manager=self.buzzer_manager,
            board_manager=self.board_manager
        )
        
        logger.info("Game service set for AI Host Service")
    
    async def send_chat_message(self, message: str):
        """Send a chat message as the AI host."""
        return await self.chat_processor.send_chat_message(message)
    
    async def synthesize_and_play_speech(self, text: str, is_question_audio=False, is_incorrect_answer_audio=False):
        """
        Synthesize speech and add it to the playback queue.
        
        Args:
            text: The text to synthesize
            is_question_audio: Whether this is the audio for a question
            is_incorrect_answer_audio: Whether this is the audio for an incorrect answer
        """
        return await self.audio_manager.synthesize_and_play_speech(text, is_question_audio, is_incorrect_answer_audio)
    
    async def monitor_game_state(self):
        """Monitor the game state and respond to changes."""
        # Delegate to the game flow manager
        await self.game_flow_manager.monitor_game_state()
    
    async def process_chat_message(self, username: str, message: str):
        """
        Process a chat message from a player and determine if action is needed.
        
        Args:
            username: The player's username
            message: The content of the chat message
        """
        # Forward to the chat processor
        await self.chat_processor.process_chat_message(username, message)
    
    async def run(self):
        """Main game loop for monitoring the game and managing interactions."""
        logger.info("Starting AI host game loop")
        
        try:
            game_error_count = 0
            max_errors = 5
            
            while True:
                try:
                    # Monitor the game state using the game flow manager
                    await self.monitor_game_state()
                    
                    # Small delay between checks
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    game_error_count += 1
                    logger.error(f"Error in game loop (attempt {game_error_count}/{max_errors}): {e}")
                    
                    # Log traceback for debugging
                    import traceback
                    logger.error(traceback.format_exc())
                    
                    # Longer backoff on repeated errors
                    await asyncio.sleep(2)
                    
                    # Reset error count after maxing out
                    if game_error_count > max_errors:
                        game_error_count = 0
                        
        except Exception as e:
            logger.error(f"Fatal error in game loop: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def handle_audio_completed(self, audio_id: str):
        """
        Handle notification that an audio has completed playing.
        
        Args:
            audio_id: The ID of the audio that finished playing
        """
        # Delegate to the buzzer manager
        await self.buzzer_manager.handle_audio_completed(audio_id) 