"""
Game state management for the AI Host.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional, Set, List

logger = logging.getLogger(__name__)

@dataclass
class Question:
    text: str
    answer: Optional[str]
    category: str
    value: int
    timestamp: float = 0  # When the question was displayed

class QuestionState:
    """Tracks the state of the current question."""
    
    def __init__(self):
        self.text = ""
        self.answer = ""
        self.category = ""
        self.value = 0
        self.timestamp = None

class GameState:
    """
    Tracks the state of the game, including current question, players, etc.
    """
    
    def __init__(self):
        self.players = set()
        self.current_question = None
        self.buzzed_player = None
        self.incorrect_players = set()
        self.player_with_control = None
        self.expected_player_count = 0
        
        # Message tracking
        self.processed_messages = set()
        self.question_processed_messages = set()
        
        # For more reliable message detection - messages when a player buzzed in
        self.baseline_buzz_messages = set()
        # For more reliable clue selection - messages when a player got control
        self.baseline_control_messages = set()
        
        # Game state flags
        self.game_started = False
        self.welcome_completed = False
        self.waiting_for_preferences = False
        self.preference_countdown_started = False
        self.preference_collection_start_time = 0
        self.preference_countdown_time = 0
        
        # Question tracking
        self.read_questions = set()
        
        # Debug counter
        self.preference_check_count = 0
        
        # New field to track when a player buzzed in
        self.buzz_timestamp = 0
    
    def add_player(self, name: str):
        """Add a player to the game."""
        self.players.add(name)
        logger.info(f"Added player {name}, current players: {self.players}")
    
    def get_player_names(self) -> List[str]:
        """Get a list of all player names."""
        return list(self.players)
    
    def set_question(self, text: str, answer: str, category: str, value: int):
        """Set the current question."""
        self.current_question = QuestionState()
        self.current_question.text = text
        self.current_question.answer = answer
        self.current_question.category = category
        self.current_question.value = value
        self.current_question.timestamp = time.time()
        
        # Reset per-question state
        self.buzzed_player = None
        self.incorrect_players = set()
        self.question_processed_messages = set()
    
    def reset_question(self):
        """Reset the current question state."""
        self.current_question = None
        self.buzzed_player = None
        self.incorrect_players = set()
        self.buzz_timestamp = 0  # Reset the buzz timestamp
        self.question_processed_messages.clear()  # Clear question-specific processed messages
    
    def set_buzzed_player(self, player_name: str, processed_messages: Set[str] = None):
        """
        Set the player who buzzed in.
        
        Args:
            player_name: Name of the player who buzzed in
            processed_messages: Set of message IDs to mark as processed
        """
        self.buzzed_player = player_name
        self.buzz_timestamp = time.time()  # Record when the player buzzed in (keeping for backwards compatibility)
        
        # Store baseline messages to detect new ones after buzzing
        if processed_messages:
            self.baseline_buzz_messages = processed_messages.copy()
            self.question_processed_messages.update(processed_messages)
    
    def reset_buzzed_player(self):
        """Reset the buzzed player without clearing other question state."""
        self.buzzed_player = None
    
    def track_incorrect_attempt(self, player_name: str):
        """Track a player who attempted to answer incorrectly."""
        self.incorrect_players.add(player_name)
    
    def all_players_attempted(self) -> bool:
        """Check if all players have attempted to answer the current question."""
        if not self.players:
            return False
        
        return len(self.incorrect_players) >= len(self.players) - 1
    
    def should_check_answers(self) -> bool:
        """Check if we should be monitoring for player answers."""
        return (self.current_question is not None and 
                self.buzzed_player is not None and 
                self.buzzed_player not in self.incorrect_players)
    
    def should_check_for_clue_selection(self) -> bool:
        """Check if we should be monitoring for clue selection."""
        return (self.current_question is None and 
                self.game_started and 
                self.player_with_control is not None)
    
    def set_player_with_control(self, player_name: str, processed_messages: Set[str] = None):
        """Set the player who has control of the board."""
        self.player_with_control = player_name
        
        # Store baseline messages to detect new ones after getting control
        if processed_messages:
            self.baseline_control_messages = processed_messages.copy()
            self.processed_messages.update(processed_messages)
    
    def get_player_with_control(self) -> Optional[str]:
        """Get the player who has control of the board."""
        return self.player_with_control
    
    def set_expected_player_count(self, count: int):
        """Set the expected number of players for the game."""
        self.expected_player_count = count
    
    def is_message_new(self, message_key: str) -> bool:
        """Check if a message is new (not yet processed)."""
        return message_key not in self.processed_messages
    
    def mark_message_processed(self, message_key: str):
        """Mark a message as processed."""
        self.processed_messages.add(message_key)
    
    def has_question_been_read(self, question_text: str) -> bool:
        """Check if a question has already been read aloud."""
        return question_text in self.read_questions
    
    def mark_question_read(self, question_text: str):
        """Mark a question as having been read aloud."""
        self.read_questions.add(question_text)
    
    def set_game_started(self, started: bool):
        """Set the game started flag."""
        self.game_started = started
    
    def is_game_started(self) -> bool:
        """Check if the game has started."""
        return self.game_started
    
    def set_welcome_completed(self, completed: bool):
        """Set the welcome completed flag."""
        self.welcome_completed = completed
    
    def is_welcome_completed(self) -> bool:
        """Check if the welcome message has been completed."""
        return self.welcome_completed
    
    def set_waiting_for_preferences(self, waiting: bool):
        """Set the waiting for preferences flag."""
        self.waiting_for_preferences = waiting
        
        # Initialize the timer when we start waiting
        if waiting and self.preference_collection_start_time == 0:
            self.preference_collection_start_time = time.time()
            logger.info(f"Started preference collection timer at {self.preference_collection_start_time}")
    
    def is_waiting_for_preferences(self) -> bool:
        """Check if we're waiting for player preferences."""
        # Debug counter to track preference state
        self.preference_check_count += 1
        if self.preference_check_count % 10 == 0:  # Log every 10 checks
            logger.debug(f"waiting_for_preferences={self.waiting_for_preferences}, " +
                        f"preference_countdown_started={self.preference_countdown_started}, " +
                        f"collection_time={self.preference_collection_start_time}")
        return self.waiting_for_preferences
    
    def is_message_new_after_buzz(self, message_key: str) -> bool:
        """
        Check if a message is new after the player buzzed in, without using timestamps.
        
        Args:
            message_key: Unique identifier for the message
            
        Returns:
            True if the message is new after the buzz, False otherwise
        """
        # First check if the message was already in our baseline when the player buzzed in
        if message_key in self.baseline_buzz_messages:
            # Message was already present when player buzzed in, so it's not a new answer
            return False
            
        # Then check if we've already processed this message
        if message_key in self.processed_messages or message_key in self.question_processed_messages:
            return False
            
        # If it passes both checks, it's a new message after the buzz
        return True
        
    def is_message_new_after_control(self, message_key: str) -> bool:
        """
        Check if a message is new after a player got control, without using timestamps.
        
        Args:
            message_key: Unique identifier for the message
            
        Returns:
            True if the message is new after control was given, False otherwise
        """
        # First check if the message was already in our baseline when the player got control
        if message_key in self.baseline_control_messages:
            return False
            
        # Then check if we've already processed this message
        if message_key in self.processed_messages:
            return False
            
        # If it passes both checks, it's a new message after control was given
        return True 