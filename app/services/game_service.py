from typing import Optional, Dict, Any, List
from fastapi import WebSocket
import asyncio
import time
from ..models.board import Board, BuzzerStatus, BuzzEvent
from ..models.question import Question
from ..models.contestant import Contestant
from ..models.finaljeopardy import FinalJeopardyQuestionResponse
from ..websockets.connection_manager import ConnectionManager
import logging
from ..models.game_state import GameStateManager
from ..ai.llm_state_manager import LLMStateManager
from ..ai.host import AIHostService
from ..ai.host.buzzer_manager import BuzzerManager
import json
import os
from pathlib import Path
import re

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class GameService:
    # Constants for topic names - should match JavaScript client
    BUZZER_TOPIC = "com.sc2ctl.jeopardy.buzzer"
    BUZZER_STATUS_TOPIC = "com.sc2ctl.jeopardy.buzzer_status"
    QUESTION_DISPLAY_TOPIC = "com.sc2ctl.jeopardy.question_display"
    QUESTION_DISMISS_TOPIC = "com.sc2ctl.jeopardy.question_dismiss"
    QUESTION_ANSWER_TOPIC = "com.sc2ctl.jeopardy.answer"
    CONTESTANT_SCORE_TOPIC = "com.sc2ctl.jeopardy.contestant_score"
    DAILY_DOUBLE_BET_TOPIC = "com.sc2ctl.jeopardy.daily_double_bet"
    FINAL_JEOPARDY_TOPIC = "com.sc2ctl.jeopardy.final_jeopardy"
    FINAL_JEOPARDY_RESPONSES_TOPIC = "com.sc2ctl.jeopardy.final_jeopardy_responses"
    FINAL_JEOPARDY_ANSWER_TOPIC = "com.sc2ctl.jeopardy.final_jeopardy_answers"
    BOARD_INIT_TOPIC = "com.sc2ctl.jeopardy.board_init"
    AUDIO_PLAY_TOPIC = "com.sc2ctl.jeopardy.play_audio"
    AUDIO_COMPLETE_TOPIC = "com.sc2ctl.jeopardy.audio_complete"
    
    # Timeouts
    BUZZER_RESOLVE_TIMEOUT = 0.75  # seconds
    FINAL_JEOPARDY_COLLECTION_TIMEOUT = 5.5  # seconds
    
    REQUIRED_PLAYERS = 3
    
    def __init__(self, connection_manager: ConnectionManager):
        self.connection_manager = connection_manager
        self.board = None
        self.boards_path = Path("app/game_data")
        self.state = GameStateManager()
        self.llm_state = LLMStateManager()  # Initialize LLM state manager
        self.current_question = None
        self.buzzer_active = False
        self.last_buzzer = None
        self.game_ready = False
        self.completed_audio_ids = set()  # Track completed audio playbacks
        
        # Initialize the buzzer manager
        self.buzzer_manager = BuzzerManager()
        self.buzzer_manager.set_dependencies(game_service=self)
        
        # Initialize the AI host service
        self.ai_host = AIHostService(name="AI Host")
    
    async def load_board(self, board_id: str):
        """Load a board from the filesystem"""
        try:
            board_path = self.boards_path / f"{board_id}.json"
            if not board_path.exists():
                logger.error(f"Board file not found: {board_path}")
                raise FileNotFoundError(f"Board {board_id} not found")

            logger.info(f"Loading board from {board_path}")
            with open(board_path, 'r') as f:
                board_data = json.load(f)
                # Make this our current board
                self.board = board_data
                logger.info(f"Successfully loaded board: {board_id}")
                
                # Game is ready when board is loaded
                self.game_ready = True
                
                return board_data

        except Exception as e:
            logger.error(f"Error loading board {board_id}: {e}")
            raise
    
    async def select_board(self, board_id: str):
        """Load and initialize a new board"""
        try:
            board_data = await self.load_board(board_id)
            self.board = board_data
            
            # Send the board to all clients
            await self.connection_manager.broadcast_message(
                "com.sc2ctl.jeopardy.board_selected",
                {"categories": board_data["categories"]}
            )
        except Exception as e:
            logger.error(f"Error selecting board: {e}")
            # You might want to send an error message to the client here
            await self.connection_manager.broadcast_message(
                "com.sc2ctl.jeopardy.error",
                {"message": f"Failed to load board: {str(e)}"}
            )
    
    async def send_categories(self):
        """Send all categories and questions to clients"""
        await self.connection_manager.broadcast_message(
            self.BOARD_INIT_TOPIC,
            {"categories": [category.dict() for category in self.board.categories]}
        )
        
        # Update LLM state with available categories
        self.llm_state.update_categories([category.name for category in self.board.categories])
    
    def find_question(self, category_name: str, value: int):
        """Find a question in the current board"""
        if not self.board or "categories" not in self.board:
            logger.error("No board loaded or invalid board format")
            return None
            
        # Log all categories for debugging
        categories = [cat["name"] for cat in self.board["categories"]]
        logger.debug(f"Looking for '{category_name}' in categories: {categories}")

        # First try exact match
        for category in self.board["categories"]:
            if category["name"] == category_name:
                for question in category["questions"]:
                    if question["value"] == value:
                        return question
                        
        # If no exact match, try case-insensitive match
        for category in self.board["categories"]:
            if category["name"].lower() == category_name.lower():
                logger.info(f"Found case-insensitive match for category: {category['name']}")
                for question in category["questions"]:
                    if question["value"] == value:
                        return question
        
        # If still no match, try partial match (contains)
        for category in self.board["categories"]:
            if (category_name.lower() in category["name"].lower() or 
                category["name"].lower() in category_name.lower()):
                logger.info(f"Found partial match for category: '{category_name}' -> '{category['name']}'")
                for question in category["questions"]:
                    if question["value"] == value:
                        return question
        
        logger.error(f"No question found in category '{category_name}' with value ${value}")
        return None

    def mark_question_used(self, category_name: str, value: int):
        """Mark a question as used"""
        if not self.board or "categories" not in self.board:
            return

        for category in self.board["categories"]:
            if category["name"] == category_name:
                for question in category["questions"]:
                    if question["value"] == value:
                        question["used"] = True
                        break

    async def display_question(self, category_name: str, value: int):
        """Display a question to all clients"""
        if not self.game_ready:
            logger.warning("Cannot display question - waiting for players")
            await self.connection_manager.broadcast_message(
                "com.sc2ctl.jeopardy.error",
                {"message": f"Waiting for {self.REQUIRED_PLAYERS - len(self.state.contestants)} more players"}
            )
            return

        try:
            question = self.find_question(category_name, value)
            if not question:
                logger.error(f"Question not found: {category_name} ${value}")
                return

            # Mark as used in the board data
            self.mark_question_used(category_name, value)
            
            # Reset buzzer state for new question
            self.last_buzzer = None
            
            # Set buzzer to inactive initially
            self.buzzer_active = False
            
            # Check if it's a daily double
            is_daily_double = question.get("daily_double", False)
            logger.info(f"Question is daily double: {is_daily_double}")
            
            # Set up the current question data
            self.current_question = {
                "category": category_name,
                "value": value,
                "text": question["clue"],
                "answer": question["answer"],
                "daily_double": is_daily_double
            }
            
            # Handle daily double differently
            if is_daily_double:
                # For daily double, we don't show the question yet
                # Just notify that it's a daily double
                logger.info(f"Broadcasting daily double: {category_name} ${value}")
                await self.connection_manager.broadcast_message(
                    "com.sc2ctl.jeopardy.daily_double",
                    {"category": category_name, "value": value}
                )
                logger.info(f"Displayed daily double: {category_name} ${value}")
            else:
                # For regular questions, proceed as normal
                logger.info(f"Broadcasting regular question: {category_name} ${value}")
                
                # Notify the BuzzerManager about the question display
                await self.buzzer_manager.handle_question_display()
                
                # Broadcast the question to all clients
                await self.connection_manager.broadcast_message(
                    self.QUESTION_DISPLAY_TOPIC,
                    self.current_question
                )
                logger.info(f"Displayed question: {category_name} ${value}")
                
                # Update LLM state for AI players
                self.llm_state.question_displayed(
                    category=category_name, 
                    value=value, 
                    question_text=question["clue"]
                )

        except Exception as e:
            logger.error(f"Error displaying question: {e}")
    
    async def dismiss_question(self):
        """Dismiss the current question and broadcast to all clients"""
        logger.info("Dismissing question")
        
        # Always ensure buzzer is deactivated when dismissing a question
        self.buzzer_active = False
        await self.buzzer_manager.deactivate_buzzer()
        
        # Notify clients
        await self.connection_manager.broadcast_message(
            self.QUESTION_DISMISS_TOPIC,
            {}
        )
        
        # Update LLM state
        self.llm_state.question_dismissed()
        
        # Clear question state
        self.current_question = None
        self.last_buzzer = None
    
    async def change_buzzer_status(self, active: bool):
        """Change buzzer status and broadcast to all clients"""
        logger.info(f"Setting buzzer status to: {active}")
        
        # Use buzzer manager to handle state changes
        if active:
            await self.buzzer_manager.activate_buzzer()
        else:
            await self.buzzer_manager.deactivate_buzzer()
    
    async def register_player(self, websocket: WebSocket, name: str, preferences: str = ''):
        """Register a new player with the given name and preferences"""
        websocket_id = str(id(websocket))
        if self.state.register_contestant(websocket_id, name):
            # Store the player's preferences if provided
            if preferences:
                logger.info(f"Adding preferences from registration: {name}: {preferences}")
                
                # Store directly in game state manager if available
                if hasattr(self, 'ai_host') and self.ai_host and hasattr(self.ai_host, 'game_state_manager'):
                    self.ai_host.game_state_manager.add_player_preference(name, preferences)
                    
            # Broadcast updated player list
            await self.broadcast_player_list()
            
            # Check if we have enough players
            if len(self.state.contestants) >= self.REQUIRED_PLAYERS:
                self.game_ready = True
                await self.connection_manager.broadcast_message(
                    "com.sc2ctl.jeopardy.game_ready",
                    {"ready": True}
                )
            return True
        return False
    
    async def broadcast_player_list(self):
        """Send current player list to all clients"""
        players = {
            c.name: {"score": c.score} 
            for c in self.state.contestants.values()
        }
        await self.connection_manager.broadcast_message(
            "com.sc2ctl.jeopardy.player_list",
            {"players": players}
        )
    
    async def handle_buzz(self, websocket: WebSocket, timestamp: float):
        """Handle a buzz from a contestant"""
        websocket_id = str(id(websocket))
        contestant = self.state.get_contestant_by_websocket(websocket_id)
        
        if not contestant:
            logger.warning(f"Contestant not found for websocket {websocket_id}")
            return
        
        logger.info(f"Buzz received from {contestant.name} at {timestamp}")
        
        if not self.buzzer_active:
            logger.warning(f"Buzz from {contestant.name} ignored - buzzer not active")
            return
        
        logger.info(f"Buzz accepted from {contestant.name}")
        
        # Use the buzzer manager to handle the buzz event
        await self.buzzer_manager.handle_player_buzz(contestant.name)
        
        # Notify all clients of the buzz
        await self.connection_manager.broadcast_message(
            self.BUZZER_TOPIC,
            {"contestant": contestant.name, "timestamp": timestamp}
        )
        
        # Update LLM state for player buzzed in
        self.llm_state.player_buzzed_in(contestant.name)
    
    async def answer_question(self, correct: bool, contestant_name=None):
        """Handle an answer from a contestant"""
        if not self.current_question:
            logger.warning("No current question to answer")
            return
            
        # If no contestant name provided, use the last person to buzz in
        if not contestant_name:
            contestant_name = self.last_buzzer
            
        if not contestant_name:
            logger.warning("No contestant to score")
            return

        logger.info(f"Processing answer from {contestant_name}: {'correct' if correct else 'incorrect'}")
        
        score_delta = self.current_question["value"]
        daily_double = self.current_question.get("daily_double", False)
            
        contestant = self.find_contestant(contestant_name)
        if not contestant:
            logger.warning(f"Contestant {contestant_name} not found")
            return
            
        # Broadcast the answer result
        await self.connection_manager.broadcast_message(
            self.QUESTION_ANSWER_TOPIC,
            {
                "contestant": contestant_name,
                "correct": correct,
                "value": score_delta,
                "answer": self.current_question["answer"]
            }
        )
            
        # Handle correct answer
        if correct:
            logger.info(f"Correct answer from {contestant_name}")
            
            # Award points
            contestant.score += score_delta
            
            # Use the buzzer manager to handle the correct answer
            await self.buzzer_manager.handle_correct_answer(contestant_name)
            
            # If this was a daily double or all questions have been answered, we're done
            if daily_double or self.all_questions_answered():
                await self.dismiss_question()
            else:
                # Let the contestant choose the next question
                await self.connection_manager.broadcast_message(
                    "com.sc2ctl.jeopardy.select_question",
                    {"contestant": contestant_name}
                )
                
                # Update LLM state for selecting question
                self.llm_state.selecting_question(contestant_name)
            
            # Broadcast score update
            await self.send_contestant_scores()
            
            # Update LLM state with new score
            self.llm_state.update_player_score(contestant_name, contestant.score)
            
        # Handle incorrect answer
        else:
            logger.info(f"Incorrect answer from {contestant_name}")
            
            # Deduct points for incorrect answers
            contestant.score -= score_delta
            
            # Use the buzzer manager to handle incorrect answer
            await self.buzzer_manager.handle_incorrect_answer(contestant_name)
            
            # Broadcast score update
            await self.send_contestant_scores()
            
            # Update LLM state with new score
            self.llm_state.update_player_score(contestant_name, contestant.score)
    
    async def handle_daily_double_bet(self, contestant: str, bet: int):
        """Handle a daily double bet from a contestant"""
        logger.info(f"Daily double bet: {contestant} bets ${bet}")
        
        if not self.current_question:
            logger.warning("No current question for daily double bet")
            return
            
        # Validate bet is within allowed range
        player = self.find_contestant(contestant)
        if not player:
            logger.warning(f"Contestant {contestant} not found")
            return
            
        max_bet = max(1000, player.score)
        if bet < 5 or bet > max_bet:
            logger.warning(f"Invalid bet amount: ${bet}. Must be between $5 and ${max_bet}")
            return
            
        # Store bet amount and contestant in current question
        self.current_question["value"] = bet
        self.current_question["contestant"] = contestant  # Add contestant to the question object
        
        # First send a response to confirm the bet was placed
        # This is what the frontend is looking for
        await self.connection_manager.broadcast_message(
            "com.sc2ctl.jeopardy.daily_double_bet_response",
            {
                "question": self.current_question,
                "bet": bet,
                "contestant": contestant
            }
        )
        
        # Then display the question after the bet is confirmed
        await self.connection_manager.broadcast_message(
            self.QUESTION_DISPLAY_TOPIC,
            self.current_question
        )
            
        # For daily doubles, the contestant who selected it automatically gets to answer
        # So we don't activate the buzzer for everyone
        self.last_buzzer = contestant
        
        # Update LLM state
        self.llm_state.question_displayed(
            category=self.current_question["category"],
            value=bet,
            question_text=self.current_question["text"]
        )
        
        # After showing the question, the next step is for the player to answer
        # Update LLM state for awaiting answer
        self.llm_state.player_buzzed_in(contestant)
    
    async def handle_final_jeopardy_request(self, content_type: str):
        """Handle a request for final jeopardy content"""
        clue = self.board.final_jeopardy_state.clue
        
        payload = {}
        if content_type == "category":
            payload = {"category": clue.category}
        elif content_type == "clue":
            payload = {"clue": clue.clue}
        elif content_type == "answer":
            payload = {"answer": clue.answer}
        
        await self.connection_manager.broadcast_to_topic(
            self.FINAL_JEOPARDY_TOPIC,
            {
                "topic": self.FINAL_JEOPARDY_TOPIC,
                "payload": payload
            }
        )
    
    async def handle_final_jeopardy_bet(self, contestant: str, bet: int):
        """Handle a final jeopardy bet"""
        self.board.final_jeopardy_state.set_bet(contestant, bet)
    
    async def handle_final_jeopardy_answer(self, contestant: str, answer: str):
        """Handle a final jeopardy answer"""
        self.board.final_jeopardy_state.set_answer(contestant, answer)
    
    async def request_final_jeopardy_bets(self):
        """Request final jeopardy bets from all contestants"""
        if not self.board:
            logger.warning("Cannot start Final Jeopardy - no board loaded")
            return
            
        # Get final jeopardy question
        final_jeopardy = self.board.final_jeopardy_state
        
        # Send category first
        await self.connection_manager.broadcast_message(
            self.FINAL_JEOPARDY_TOPIC,
            {"type": "category", "category": final_jeopardy.category}
        )
        
        # Request bets
        await self.connection_manager.broadcast_message(
            self.FINAL_JEOPARDY_TOPIC,
            {"type": "bet"}
        )
        
        # For each AI player, update their state to making a wager
        for contestant in self.board.contestants:
            # Update LLM state for making wager
            self.llm_state.making_wager(
                player_name=contestant.name,
                wager_type="Final Jeopardy",
                max_wager=contestant.score
            )
    
    async def check_final_jeopardy_bets_after_timeout(self):
        """Check if all bets are received after timeout"""
        await asyncio.sleep(self.FINAL_JEOPARDY_COLLECTION_TIMEOUT)
        
        if not self.board.final_jeopardy_state.has_all_bets():
            missing = self.board.final_jeopardy_state.get_missing_bets()
            print(f"Did not receive all final jeopardy bets! Missing: {', '.join(missing)}")
        
        # Show clue anyway
        await self.handle_final_jeopardy_request("clue")
    
    async def request_final_jeopardy_answers(self):
        """Request answers from all contestants"""
        await self.connection_manager.broadcast_to_topic(
            self.FINAL_JEOPARDY_RESPONSES_TOPIC,
            {
                "topic": self.FINAL_JEOPARDY_RESPONSES_TOPIC,
                "payload": {"content": "answer"}
            }
        )
        
        # Start timer to show answer anyway after timeout
        asyncio.create_task(self.check_final_jeopardy_answers_after_timeout())
    
    async def check_final_jeopardy_answers_after_timeout(self):
        """Check if all answers are received after timeout"""
        await asyncio.sleep(self.FINAL_JEOPARDY_COLLECTION_TIMEOUT)
        
        if not self.board.final_jeopardy_state.has_all_answers():
            missing = self.board.final_jeopardy_state.get_missing_answers()
            print(f"Did not receive all final jeopardy answers! Missing: {', '.join(missing)}")
        
        # Show answer anyway
        await self.handle_final_jeopardy_request("answer")
    
    async def get_final_jeopardy_response(self, contestant: str):
        """Get a contestant's final jeopardy response"""
        response = self.board.final_jeopardy_state.get_response(contestant)
        
        if not response:
            # No answer provided
            payload = {
                "contestant": contestant,
                "bet": 0,
                "answer": "No answer provided"
            }
        else:
            payload = response.dict()
        
        await self.connection_manager.broadcast_to_topic(
            self.FINAL_JEOPARDY_ANSWER_TOPIC,
            {
                "topic": self.FINAL_JEOPARDY_ANSWER_TOPIC,
                "payload": payload
            }
        )

    async def send_game_state(self, websocket: WebSocket):
        """Send current game state to new connection"""
        if self.board:
            await self.connection_manager.send_personal_message(
                websocket,
                "com.sc2ctl.jeopardy.board_selected",
                {"categories": self.board["categories"]}
            )
        
        if self.current_question:
            await self.connection_manager.send_personal_message(
                websocket,
                self.QUESTION_DISPLAY_TOPIC,
                self.current_question
            )
        
        await self.connection_manager.send_personal_message(
            websocket,
            self.BUZZER_STATUS_TOPIC,
            {"active": self.buzzer_active}
        )

    def find_contestant(self, name: str):
        """Find a contestant by name"""
        for contestant_id, contestant in self.state.contestants.items():
            if contestant.name == name:
                return contestant
        return None

    def all_questions_answered(self) -> bool:
        """Check if all questions have been answered"""
        if not self.board or "categories" not in self.board:
            return False
            
        for category in self.board["categories"]:
            for question in category["questions"]:
                if not question.get("used", False):
                    return False
        return True

    def mark_audio_completed(self, audio_id: str):
        """Mark an audio file as having completed playback"""
        logger.info(f"🔊 Marking audio as completed: {audio_id}")
        self.completed_audio_ids.add(audio_id)
        logger.debug(f"Current completed audio IDs: {list(self.completed_audio_ids)[:5]}...")
        
        # Clean up old IDs if there are too many (keep last 100)
        if len(self.completed_audio_ids) > 100:
            # Convert to list, sort by timestamp part of ID, and keep only most recent 100
            sorted_ids = sorted(
                self.completed_audio_ids, 
                key=lambda x: int(x.split('_')[-1]) if '_' in x and x.split('_')[-1].isdigit() else 0,
                reverse=True
            )
            self.completed_audio_ids = set(sorted_ids[:100])
        
        # Use the buzzer manager to handle audio completion
        asyncio.create_task(self.buzzer_manager.handle_audio_completed(audio_id))

    def check_audio_completed(self, audio_id: str) -> bool:
        """Check if an audio file has completed playback"""
        result = audio_id in self.completed_audio_ids
        logger.debug(f"Checking if audio {audio_id} completed: {result}")
        return result

    async def handle_audio_completed(self, audio_id: str):
        """Handle notification that audio playback has completed"""
        # Mark the audio as completed
        self.mark_audio_completed(audio_id)
        
        # Delegate to buzzer manager to handle logic for buzzer activation
        await self.buzzer_manager.handle_audio_completed(audio_id)

    async def startup(self):
        """Initialize the game service and start background tasks"""
        logger.info("Starting game service")
        
        # Start the AI host service
        success = await self.ai_host.start()
        if success:
            # Pass the WebSocket manager to the AI host
            self.ai_host.set_websocket_manager(self.connection_manager)
            # Pass the game service to the AI host
            self.ai_host.set_game_service(self)
            # Start the main game loop for the AI host
            asyncio.create_task(self.ai_host.run())
            
            # Set the buzzer manager's dependencies after AI host is initialized
            self.buzzer_manager.set_dependencies(
                game_service=self,
                game_state_manager=self.ai_host.game_state_manager,
                chat_processor=self.ai_host.chat_processor,
                audio_manager=self.ai_host.audio_manager
            )
            
            logger.info("AI Host Service started successfully")
        else:
            logger.error("Failed to start AI host service")
        
        # Return success
        return True

    async def handle_chat_message(self, username: str, message: str):
        """
        Handle a chat message from a player and forward it to the AI host.
        
        Args:
            username: The player's username
            message: The chat message content
        """
        logger.info(f"Chat message from {username}: {message}")
        
        # Store chat messages for preferences directly if we're in the initial game phase
        if not self.game_ready and hasattr(self, 'ai_host') and hasattr(self.ai_host, 'game_state_manager'):
            # This is a direct backup to ensure messages are collected
            logger.info(f"Directly storing chat message for preferences: {username}: {message}")
            self.ai_host.game_state_manager.recent_chat_messages.append({
                "username": username,
                "message": message
            })
        
        # Forward to AI host for processing
        if hasattr(self, 'ai_host'):
            await self.ai_host.process_chat_message(username, message)
        else:
            logger.warning("AI host not available, cannot process chat message")

    async def dismiss_current_question(self):
        """Dismiss the current question and notify all clients"""
        if self.current_question:
            # Mark the question as used
            category = self.current_question["category"]
            value = self.current_question["value"]
            
            # Find and mark the question as used
            for cat in self.board.categories:
                if cat.name == category:
                    for question in cat.questions:
                        if question.value == value:
                            question.used = True
                            break
        
        # Call our main dismiss_question method to handle the rest
        await self.dismiss_question()

    async def send_buzzer_status(self):
        """Send current buzzer status to all clients"""
        await self.connection_manager.broadcast_message(
            self.BUZZER_STATUS_TOPIC,
            {"active": self.buzzer_active}
        )

    async def send_contestant_scores(self):
        """Send current contestant scores to all clients"""
        scores = {
            contestant.name: contestant.score 
            for contestant in self.state.contestants.values()
        }
        await self.connection_manager.broadcast_message(
            self.CONTESTANT_SCORE_TOPIC,
            {"scores": scores}
        )

    async def play_audio(self, audio_url: str, wait_for_completion: bool = True, audio_id: str = None):
        """
        Play audio on all connected clients
        
        Args:
            audio_url: The URL of the audio file to play
            wait_for_completion: Whether to send a completion event when audio finishes
            audio_id: Optional unique ID for this audio playback
        """
        # If no audio_id provided, try to extract it from the filename
        if not audio_id:
            # Try to extract timestamp from filename (e.g., question_audio_1234567890.wav)
            match = re.search(r'question_audio_(\d+)', audio_url)
            if match:
                # Use the timestamp from the filename
                audio_id = f"audio_{match.group(1)}"
            else:
                # Fallback to generating a new ID
                audio_id = f"audio_{int(time.time() * 1000)}"
        
        logger.info(f"🔊 Broadcasting audio playback: {audio_url} (ID: {audio_id}, wait: {wait_for_completion})")
        
        # Support both message formats - keep as 'url' for backward compatibility with existing UI code
        # but also include as audio_url for newer code
        await self.connection_manager.broadcast_message(
            self.AUDIO_PLAY_TOPIC,
            {
                "url": audio_url,  # For backward compatibility
                "audio_url": audio_url,  # For newer code
                "audio_id": audio_id,
                "wait_for_completion": wait_for_completion
            }
        )
        
        return audio_id 