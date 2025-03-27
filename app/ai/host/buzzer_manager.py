"""
Buzzer Manager for handling buzzer-related functionality in the Jeopardy game.
"""

import logging
import asyncio
import time
from typing import Set, Optional

logger = logging.getLogger(__name__)

class BuzzerManager:
    """
    Manages the buzzer state, timeouts, and related functionality.
    Acts as the central authority for buzzer state across the system.
    """
    
    def __init__(self):
        """Initialize the buzzer manager."""
        # Buzzer state tracking
        self.last_buzzer = None
        self.buzzer_active = False
        self.incorrect_players = set()  # Track players who answered incorrectly
        self.expecting_reactivation = False  # Flag to track if we're expecting to reactivate after audio
        
        # Timeout management
        self.buzzer_timeout_task = None
        self.buzzer_timeout_seconds = 5.0  # 5 second timeout
        self.is_timeout_active = False
        
        # Answer timeout management
        self.answer_timeout_task = None
        self.answer_timeout_seconds = 7.0  # 7 second timeout for answering
        self.answer_timeout_active = False
        
        # Dependencies (to be set later)
        self.game_service = None
        self.game_state_manager = None
        self.chat_processor = None
        self.audio_manager = None
    
    def set_dependencies(self, game_service=None, game_state_manager=None, 
                         chat_processor=None, audio_manager=None):
        """Set dependencies required for buzzer management."""
        if game_service:
            self.game_service = game_service
        if game_state_manager:
            self.game_state_manager = game_state_manager
        if chat_processor:
            self.chat_processor = chat_processor
        if audio_manager:
            self.audio_manager = audio_manager
    
    async def activate_buzzer(self):
        """Activate the buzzer and broadcast state to all clients."""
        if not self.buzzer_active:
            logger.info("Activating buzzer")
            self.buzzer_active = True
            
            # Update game state manager if available
            if self.game_state_manager:
                self.game_state_manager.buzzer_active = True
            
            # Update game service state if available
            if self.game_service:
                self.game_service.buzzer_active = True
                await self.game_service.connection_manager.broadcast_message(
                    "com.sc2ctl.jeopardy.buzzer_status",
                    {"active": True}
                )
            
            # Start timeout for buzzer
            self.start_timeout()
    
    async def deactivate_buzzer(self):
        """Deactivate the buzzer and broadcast state to all clients."""
        if self.buzzer_active:
            logger.info("Deactivating buzzer")
            self.buzzer_active = False
            
            # Update game state manager if available
            if self.game_state_manager:
                self.game_state_manager.buzzer_active = False
            
            # Update game service state if available
            if self.game_service:
                self.game_service.buzzer_active = False
                await self.game_service.connection_manager.broadcast_message(
                    "com.sc2ctl.jeopardy.buzzer_status",
                    {"active": False}
                )
            
            # Cancel any active timeout
            self.cancel_timeout()
    
    async def handle_question_display(self):
        """Handle when a question is displayed, making sure buzzer is disabled."""
        logger.info("Question displayed, ensuring buzzer is disabled")
        await self.deactivate_buzzer()
        
        # Reset state for new question
        self.incorrect_players.clear()
        self.last_buzzer = None
        self.cancel_answer_timeout()  # Cancel any active answer timeout
    
    async def handle_audio_completed(self, audio_id: str):
        """
        Handle notification that an audio has completed playing.
        
        Args:
            audio_id: The ID of the audio that finished playing
        """
        try:
            logger.info(f"Audio completed notification: {audio_id}")
            
            # Track already processed audio IDs to prevent duplicate handling
            if hasattr(self, '_processed_audio_ids'):
                if audio_id in self._processed_audio_ids:
                    logger.info(f"Already processed audio completion for {audio_id}, skipping")
                    return
                self._processed_audio_ids.add(audio_id)
            else:
                # Initialize the set on first call
                self._processed_audio_ids = {audio_id}
                
            # Limit the size of the set to prevent memory leaks
            if len(self._processed_audio_ids) > 100:
                # Keep only the most recent 50 IDs
                self._processed_audio_ids = set(list(self._processed_audio_ids)[-50:])
            
            # Clear audio IDs but don't rely on them for timer decision
            if self.audio_manager:
                self.audio_manager.check_and_clear_audio_ids(audio_id)
            
            # Check if this is an incorrect answer audio completion
            if "incorrect" in audio_id and self.expecting_reactivation:
                logger.info("Incorrect answer audio completed, now reactivating buzzer for other players")
                
                # Reset flag
                self.expecting_reactivation = False
                
                # Check if we still have a current question and other players available
                if self.game_service and self.game_service.current_question:
                    # Get all players and incorrect players
                    all_players = set()
                    if self.game_state_manager:
                        all_players = set(self.game_state_manager.get_player_names())
                    
                    if len(self.incorrect_players) < len(all_players):
                        logger.info(f"Not all players have attempted, reactivating buzzer. "
                                    f"Incorrect: {len(self.incorrect_players)}, Total: {len(all_players)}")
                        
                        # Activate the buzzer for other players
                        await self.activate_buzzer()
                        
                        # Update game state manager buzzer state
                        if self.game_state_manager:
                            self.game_state_manager.buzzer_active = True
                    else:
                        # All players have attempted, dismiss the question
                        logger.info("All players have attempted, dismissing question")
                        if self.game_service:
                            await self.game_service.dismiss_question()
                
                return
            
            # Check if we're expecting to reactivate the buzzer after regular audio
            elif self.expecting_reactivation and self.game_service and self.game_service.current_question:
                logger.info("Regular audio completed with reactivation flag set, activating buzzer")
                
                # Reset flag
                self.expecting_reactivation = False
                
                # Activate the buzzer for other players
                await self.activate_buzzer()
                
                # Update game state manager buzzer state
                if self.game_state_manager:
                    self.game_state_manager.buzzer_active = True
                
                return
            
            # Normal case: Only activate buzzer if there's a current question and no one has buzzed yet
            if (self.game_service and self.game_service.current_question 
                and not self.game_service.last_buzzer):
                
                logger.info("Question audio completed, activating buzzer")
                
                # Clear any existing incorrect player tracking
                self.incorrect_players.clear()
                if self.game_state_manager:
                    self.game_state_manager.clear_incorrect_attempts()
                
                # Activate the buzzer
                await self.activate_buzzer()
                
                # Update game state manager buzzer state
                if self.game_state_manager:
                    self.game_state_manager.buzzer_active = True
            else:
                if not (self.game_service and self.game_service.current_question):
                    logger.info("Not activating buzzer - no active question")
                elif self.game_service.last_buzzer:
                    logger.info(f"Not activating buzzer - player {self.game_service.last_buzzer} already buzzed")
                else:
                    logger.info("Not activating buzzer - unknown reason")
                
        except Exception as e:
            logger.error(f"Error handling audio completion: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def handle_player_buzz(self, player_name: str):
        """Handle when a player buzzes in."""
        logger.info(f"Player {player_name} buzzed in")
        
        # Record the player who buzzed in
        self.last_buzzer = player_name
        
        # Always deactivate the buzzer when someone buzzes in
        await self.deactivate_buzzer()
        
        # Cancel any active timeout
        self.cancel_timeout()
        
        # Update game state manager
        if self.game_state_manager:
            self.game_state_manager.set_buzzed_player(player_name, self.incorrect_players)
            self.game_state_manager.buzzer_active = False
        
        # Update game service if available
        if self.game_service:
            self.game_service.last_buzzer = player_name
            
            # Start answer timeout and notify frontend
            self.start_answer_timeout(player_name)
            await self.game_service.connection_manager.broadcast_message(
                "com.sc2ctl.jeopardy.answer_timer_start",
                {"player": player_name, "seconds": self.answer_timeout_seconds}
            )
    
    async def handle_incorrect_answer(self, player_name: str):
        """Handle when a player gives an incorrect answer."""
        logger.info(f"Incorrect answer from {player_name}")
        
        # Cancel the answer timeout
        self.cancel_answer_timeout()
        
        # Add player to the set of incorrect players
        self.incorrect_players.add(player_name)
        
        # Track incorrect attempt in game state
        if self.game_state_manager:
            self.game_state_manager.track_incorrect_attempt(player_name)
        
        # Reset buzzer state
        self.last_buzzer = None
        
        # Don't activate buzzer yet - audio will play first
        # Instead, set flag so audio completion will activate it
        self.expecting_reactivation = True
        logger.info("Set expecting_reactivation=True - buzzer will activate after audio completes")
        
        # Check if all players have attempted (this logic still needed for edge cases)
        if self.game_state_manager:
            all_players = set(self.game_state_manager.get_player_names())
            incorrect_players = self.incorrect_players
            
            if len(incorrect_players) >= len(all_players):
                # All players have attempted, keep buzzer disabled and dismiss
                logger.info("All players have attempted, dismissing question")
                self.expecting_reactivation = False  # Cancel reactivation expectation
                
                if self.game_service:
                    await self.game_service.dismiss_question()
                    
                    # Get the player with control after all incorrect answers
                    if self.game_state_manager:
                        controlling_player = self.game_state_manager.get_player_with_control()
                        if controlling_player:
                            # Small delay for UI update
                            await asyncio.sleep(0.5)
                            
                            # Inform the player with control
                            control_msg = f"{controlling_player}, you still have control of the board. Please select the next clue."
                            if self.chat_processor:
                                await self.chat_processor.send_chat_message(control_msg)
        else:
            # No game state manager, just reactivate the buzzer
            logger.warning("No game state manager available, just reactivating buzzer")
            await self.activate_buzzer()
    
    async def handle_correct_answer(self, player_name: str):
        """Handle when a player gives a correct answer."""
        logger.info(f"Correct answer from {player_name}")
        
        # Cancel the answer timeout
        self.cancel_answer_timeout()
        
        # Keep buzzer deactivated
        await self.deactivate_buzzer()
        
        # Cancel any active timeout
        self.cancel_timeout()
        
        # Update player with control in game state
        if self.game_state_manager:
            used_questions = set()
            if self.game_service and self.game_service.current_question:
                category = self.game_service.current_question["category"]
                value = self.game_service.current_question["value"]
                question_key = f"{category}:{value}"
                used_questions.add(question_key)
            
            self.game_state_manager.set_player_with_control(player_name, used_questions)
    
    def start_timeout(self):
        """Start the buzzer timeout task."""
        # Cancel any existing timeout task first
        self.cancel_timeout()
        
        # Create new timeout task and set flag
        expiry_time = time.time() + self.buzzer_timeout_seconds
        logger.info(f"Starting buzzer timeout task ({self.buzzer_timeout_seconds} seconds) - timer will expire at {expiry_time:.1f}")
        
        self.buzzer_timeout_task = asyncio.create_task(self.handle_timeout())
        self.is_timeout_active = True
    
    def cancel_timeout(self):
        """Cancel the buzzer timeout task if it exists."""
        if self.buzzer_timeout_task:
            if not self.buzzer_timeout_task.done():
                logger.info("Cancelling active buzzer timeout task")
                self.buzzer_timeout_task.cancel()
            else:
                logger.info("Buzzer timeout task already done, clearing reference")
            
            self.buzzer_timeout_task = None
            self.is_timeout_active = False
    
    def start_answer_timeout(self, player_name: str):
        """Start the answer timeout task for a specific player."""
        # Cancel any existing answer timeout task first
        self.cancel_answer_timeout()
        
        # Create new timeout task and set flag
        expiry_time = time.time() + self.answer_timeout_seconds
        logger.info(f"Starting answer timeout task for {player_name} ({self.answer_timeout_seconds} seconds) - timer will expire at {expiry_time:.1f}")
        
        self.answer_timeout_task = asyncio.create_task(self.handle_answer_timeout(player_name))
        self.answer_timeout_active = True
    
    def cancel_answer_timeout(self):
        """Cancel the answer timeout task if it exists."""
        if self.answer_timeout_task:
            if not self.answer_timeout_task.done():
                logger.info("Cancelling active answer timeout task")
                self.answer_timeout_task.cancel()
            else:
                logger.info("Answer timeout task already done, clearing reference")
            
            self.answer_timeout_task = None
            self.answer_timeout_active = False
    
    async def handle_timeout(self):
        """Handle the case when buzzer timeout expires with no one answering."""
        try:
            logger.info(f"Buzzer timeout starting - waiting {self.buzzer_timeout_seconds} seconds...")
            
            # Wait for the timeout period
            await asyncio.sleep(self.buzzer_timeout_seconds)
            
            logger.info("Buzzer timeout expired - checking if we need to handle it...")
            
            # Check if there's still an active question and no one has buzzed in
            if (self.game_service and self.game_service.current_question and not self.game_service.last_buzzer):
                logger.info("No one buzzed in - handling timeout...")
                
                # Get the current question data
                question = self.game_service.current_question
                if not question:
                    logger.warning("No question found during buzzer timeout")
                    return
                
                answer = question.get("answer", "Unknown")
                
                # Announce that time is up and reveal the answer
                # GET player with control
                if self.game_state_manager:
                    controlling_player = self.game_state_manager.get_player_with_control()
                    if controlling_player:
                        timeout_msg = f"Time's up! The correct answer was: {answer}. {controlling_player}, you still have control of the board. Please select the next clue."
                    else:
                        timeout_msg = f"Time's up! The correct answer was: {answer}"
                logger.info(f"Revealing answer: {timeout_msg}")
                
                # Send message and speak it
                if self.chat_processor:
                    await self.chat_processor.send_chat_message(timeout_msg)
                
                if self.audio_manager:
                    await self.audio_manager.synthesize_and_play_speech(timeout_msg)
                
                # Dismiss the question in the UI
                if self.game_service:
                    logger.info("Dismissing question after timeout")
                    await self.game_service.dismiss_question()
                
                # Get the player with control
                if self.game_state_manager:
                    controlling_player = self.game_state_manager.get_player_with_control()
                    if controlling_player:
                        # Small delay for UI update
                        await asyncio.sleep(0.5)
                        
                        # Prompt the player with control to select the next clue
                        next_clue_msg = f"{controlling_player}, you still have control of the board. Please select the next clue."
                        if self.chat_processor:
                            await self.chat_processor.send_chat_message(next_clue_msg)
                    else:
                        # If no player has control, find the player with the highest score
                        if self.game_service and hasattr(self.game_service, "state") and hasattr(self.game_service.state, "contestants"):
                            best_player = None
                            best_score = float('-inf')
                            
                            for contestant_id, contestant in self.game_service.state.contestants.items():
                                if contestant.score > best_score:
                                    best_score = contestant.score
                                    best_player = contestant.name
                            
                            if best_player:
                                # Set player with control in game state
                                self.game_state_manager.set_player_with_control(best_player, set())
                                
                                # Small delay for UI update
                                await asyncio.sleep(0.5)
                                
                                # Prompt the player with highest score to select the next clue
                                next_clue_msg = f"{best_player}, you have the highest score and control of the board. Please select the next clue."
                                if self.chat_processor:
                                    await self.chat_processor.send_chat_message(next_clue_msg)
                            else:
                                logger.warning("No player found with highest score after buzzer timeout")
                else:
                    logger.warning("No game state manager available during timeout, cannot determine controlling player")
            else:
                logger.info("Buzzer timeout not handled - no active question or someone already buzzed in")
                
        except asyncio.CancelledError:
            # Task was cancelled, which is expected behavior
            logger.debug("Buzzer timeout task was cancelled")
        except Exception as e:
            logger.error(f"Error in buzzer timeout handler: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def handle_answer_timeout(self, player_name: str):
        """Handle the case when a player doesn't answer within the time limit."""
        try:
            logger.info(f"Answer timeout starting for {player_name} - waiting {self.answer_timeout_seconds} seconds...")
            
            # Wait for the timeout period
            await asyncio.sleep(self.answer_timeout_seconds)
            
            logger.info(f"Answer timeout expired for {player_name} - checking if we need to handle it...")
            
            # Check if there's still an active question and the same player still has the buzzer
            if (self.game_service and self.game_service.current_question 
                and self.game_service.last_buzzer == player_name 
                and self.last_buzzer == player_name):
                
                logger.info(f"Player {player_name} didn't answer in time - marking as incorrect...")
                
                # Get the current question data
                question = self.game_service.current_question
                if not question:
                    logger.warning("No question found during answer timeout")
                    return
                
                # Announce that time is up for this player
                timeout_msg = f"Time's up, {player_name}! You didn't answer in time."
                logger.info(f"Sending timeout message: {timeout_msg}")
                
                # Send message and speak it
                if self.chat_processor:
                    await self.chat_processor.send_chat_message(timeout_msg)
                
                if self.audio_manager:
                    await self.audio_manager.synthesize_and_play_speech(timeout_msg)
                
                # Deduct points as if they answered incorrectly
                value = question.get("value", 0)
                
                # Update score
                if self.game_service:
                    # Mark incorrect without showing answer yet
                    await self.game_service.connection_manager.broadcast_message(
                        "com.sc2ctl.jeopardy.answer",
                        {
                            "contestant": player_name,
                            "correct": False,
                            "value": value
                        }
                    )
                
                # Handle this as an incorrect answer to reactivate buzzer for others
                await self.handle_incorrect_answer(player_name)
                
            else:
                logger.info(f"Answer timeout not handled - no active question, or player {player_name} no longer has control")
                
        except asyncio.CancelledError:
            # Task was cancelled, which is expected behavior
            logger.debug(f"Answer timeout task for {player_name} was cancelled")
        except Exception as e:
            logger.error(f"Error in answer timeout handler: {e}")
            import traceback
            logger.error(traceback.format_exc()) 