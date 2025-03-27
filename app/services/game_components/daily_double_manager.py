import logging
import asyncio
from typing import Dict, Any, Optional
from ..websockets.connection_manager import ConnectionManager

logger = logging.getLogger(__name__)

class DailyDoubleManager:
    DAILY_DOUBLE_BET_TOPIC = "com.sc2ctl.jeopardy.daily_double_bet"
    
    def __init__(self, connection_manager: ConnectionManager):
        self.connection_manager = connection_manager
        
    async def handle_bet(self, contestant: str, bet: int, current_question: Dict[str, Any]) -> bool:
        """Handle a daily double bet from a contestant"""
        logger.info(f"Daily double bet: {contestant} bets ${bet}")
        
        if not current_question:
            logger.warning("No current question for daily double bet")
            return False
            
        # Store bet amount and contestant in current question
        current_question["value"] = bet
        current_question["contestant"] = contestant
        
        # First send a response to confirm the bet was placed
        await self.connection_manager.broadcast_message(
            "com.sc2ctl.jeopardy.daily_double_bet_response",
            {
                "question": current_question,
                "bet": bet,
                "contestant": contestant
            }
        )
        
        # Then display the question after the bet is confirmed
        await self.connection_manager.broadcast_message(
            "com.sc2ctl.jeopardy.question_display",
            current_question
        )
            
        return True 