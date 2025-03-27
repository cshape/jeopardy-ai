from enum import Enum, auto
import json
from typing import Dict, Any, List, Optional
import logging

from .utils.llm import LLMClient, LLMConfig

logger = logging.getLogger(__name__)

class GameState(Enum):
    """Enum representing the possible states in a Jeopardy game."""
    QUESTION_DISPLAYED = auto()
    PLAYER_BUZZED_IN = auto()
    AWAITING_ANSWER = auto()
    SELECTING_QUESTION = auto()
    MAKING_WAGER = auto()
    GAME_OVER = auto()

class AIPlayer:
    """AI player for Jeopardy game using LLM for decision making."""
    
    def __init__(self, name: str, personality: str = "competitive and knowledgeable"):
        """
        Initialize an AI player.
        
        Args:
            name: The name of the AI player
            personality: A short description of the player's personality
        """
        self.name = name
        self.personality = personality
        self.llm_client = LLMClient()
        self.current_state: Dict[str, Any] = {}
        self.game_history: List[Dict[str, Any]] = []
        
        # Create a response format that enforces JSON
        self.llm_config = LLMConfig(
            temperature=0.7,
            response_format={"type": "json_object"}
        )
        
    def update_state(self, state: Dict[str, Any]) -> None:
        """
        Update the AI player's knowledge of the current game state.
        
        Args:
            state: Dictionary containing current game state information
        """
        # Keep track of previous states for context
        if self.current_state:
            self.game_history.append(self.current_state)
            # Limit history size to avoid token limits
            if len(self.game_history) > 10:
                self.game_history.pop(0)
        
        self.current_state = state
    
    async def get_action(self) -> Dict[str, Any]:
        """
        Get the AI player's action based on the current game state.
        
        Returns:
            Dictionary with action and any associated data
        """
        if not self.current_state:
            return {"action": "pass", "reason": "No game state available"}
        
        # Get template and context based on current state
        state_str = self.current_state.get("state", "UNKNOWN")
        template, context = self._get_template_and_context(state_str)
        
        try:
            # Call the LLM with templates
            response_text = await self.llm_client.chat_with_template(
                user_template=template,
                user_context=context,
                system_template="player_system_prompt.j2",
                system_context={"name": self.name, "personality": self.personality},
                config=self.llm_config
            )
            
            # Parse the JSON response
            try:
                response = json.loads(response_text)
                logger.debug(f"AI Player {self.name} action: {response}")
                return response
            except json.JSONDecodeError:
                logger.error(f"Failed to parse LLM response as JSON: {response_text}")
                return {"action": "pass", "reason": "Error parsing response"}
                
        except Exception as e:
            logger.error(f"Error getting AI action: {str(e)}")
            return {"action": "pass", "reason": f"Error: {str(e)}"}
    
    def _get_template_and_context(self, state_str: str) -> tuple[str, Dict[str, Any]]:
        """
        Get the appropriate template and context for the current state.
        
        Args:
            state_str: String representation of the current state
            
        Returns:
            Tuple of (template_name, context_dict)
        """
        if state_str == "QUESTION_DISPLAYED":
            return "question_prompt.j2", {
                "category": self.current_state.get("category", "Unknown Category"),
                "question": self.current_state.get("question_text", "Unknown Question"),
                "value": self.current_state.get("value", 0)
            }
        elif state_str == "AWAITING_ANSWER":
            return "answer_prompt.j2", {
                "category": self.current_state.get("category", "Unknown Category"),
                "question": self.current_state.get("question_text", "Unknown Question")
            }
        elif state_str == "SELECTING_QUESTION":
            return "selection_prompt.j2", {
                "categories": ", ".join(self.current_state.get("available_categories", [])),
                "values": ", ".join([str(v) for v in self.current_state.get("available_values", [])])
            }
        elif state_str == "MAKING_WAGER":
            return "wager_prompt.j2", {
                "wager_type": self.current_state.get("wager_type", "Unknown"),
                "max_wager": self.current_state.get("max_wager", 0),
                "current_score": self.current_state.get("player_score", 0)
            }
        else:
            return "generic_prompt.j2", {
                "current_state": json.dumps(self.current_state),
                "game_history": json.dumps(self.game_history[-3:] if self.game_history else [])
            } 