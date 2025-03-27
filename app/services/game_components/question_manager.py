import logging
from typing import Dict, Any, Optional
from ..websockets.connection_manager import ConnectionManager
from .board_manager import BoardManager
from .buzzer_manager import BuzzerManager

logger = logging.getLogger(__name__)

class QuestionManager:
    QUESTION_DISPLAY_TOPIC = "com.sc2ctl.jeopardy.question_display"
    QUESTION_DISMISS_TOPIC = "com.sc2ctl.jeopardy.question_dismiss"
    QUESTION_ANSWER_TOPIC = "com.sc2ctl.jeopardy.answer"
    
    def __init__(self, connection_manager: ConnectionManager, board_manager: BoardManager, buzzer_manager: BuzzerManager):
        self.connection_manager = connection_manager
        self.board_manager = board_manager
        self.buzzer_manager = buzzer_manager
        self.current_question = None
        
    async def display_question(self, category_name: str, value: int, game_ready: bool = True) -> None:
        """Display a question to all clients"""
        if not game_ready:
            logger.warning("Cannot display question - game not ready")
            await self.connection_manager.broadcast_message(
                "com.sc2ctl.jeopardy.error",
                {"message": "Game not ready - waiting for players"}
            )
            return

        try:
            question = self.board_manager.find_question(category_name, value)
            if not question:
                logger.error(f"Question not found: {category_name} ${value}")
                return

            # Mark as used and clear buzzer state
            self.board_manager.mark_question_used(category_name, value)
            self.buzzer_manager.clear_state()
            
            # Check if it's a daily double
            is_daily_double = question.get("daily_double", False)
            logger.info(f"Question is daily double: {is_daily_double}")
            
            self.current_question = {
                "category": category_name,
                "value": value,
                "text": question["clue"],
                "answer": question["answer"],
                "daily_double": is_daily_double
            }
            
            if is_daily_double:
                # For daily double, we don't show the question yet
                logger.info(f"Broadcasting daily double: {category_name} ${value}")
                await self.connection_manager.broadcast_message(
                    "com.sc2ctl.jeopardy.daily_double",
                    {"category": category_name, "value": value}
                )
            else:
                # For regular questions, proceed as normal
                logger.info(f"Broadcasting regular question: {category_name} ${value}")
                await self.connection_manager.broadcast_message(
                    self.QUESTION_DISPLAY_TOPIC,
                    self.current_question
                )
                
                # Activate the buzzer for regular questions
                await self.buzzer_manager.change_status(True)

        except Exception as e:
            logger.error(f"Error displaying question: {e}")
            
    async def dismiss_question(self) -> None:
        """Dismiss the current question and broadcast to all clients"""
        logger.info("Dismissing question")
        
        # Reset the buzzer status first
        await self.buzzer_manager.change_status(False)
        
        # Notify clients
        await self.connection_manager.broadcast_message(
            self.QUESTION_DISMISS_TOPIC,
            {}
        )
        
        # Clear question state
        self.current_question = None
        self.buzzer_manager.clear_state()
        
    async def handle_answer(self, contestant_name: str, correct: bool, score_delta: Optional[int] = None) -> None:
        """Handle an answer from a contestant"""
        if not self.current_question:
            logger.warning("No current question to answer")
            return
            
        if score_delta is None:
            score_delta = self.current_question["value"]
            
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