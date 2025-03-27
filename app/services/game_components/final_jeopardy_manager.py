import logging
import asyncio
from typing import Dict, Any, Optional
from ..websockets.connection_manager import ConnectionManager

logger = logging.getLogger(__name__)

class FinalJeopardyManager:
    FINAL_JEOPARDY_TOPIC = "com.sc2ctl.jeopardy.final_jeopardy"
    FINAL_JEOPARDY_RESPONSES_TOPIC = "com.sc2ctl.jeopardy.final_jeopardy_responses"
    FINAL_JEOPARDY_ANSWER_TOPIC = "com.sc2ctl.jeopardy.final_jeopardy_answers"
    COLLECTION_TIMEOUT = 5.5  # seconds
    
    def __init__(self, connection_manager: ConnectionManager):
        self.connection_manager = connection_manager
        self.state = None  # Will hold the final jeopardy state from board
        
    def set_state(self, final_jeopardy_state: Any) -> None:
        """Set the final jeopardy state"""
        self.state = final_jeopardy_state
        
    async def handle_content_request(self, content_type: str) -> None:
        """Handle a request for final jeopardy content"""
        if not self.state or not self.state.clue:
            logger.warning("No final jeopardy state or clue available")
            return
            
        clue = self.state.clue
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
        
    async def handle_bet(self, contestant: str, bet: int) -> None:
        """Handle a final jeopardy bet"""
        if self.state:
            self.state.set_bet(contestant, bet)
            
    async def handle_answer(self, contestant: str, answer: str) -> None:
        """Handle a final jeopardy answer"""
        if self.state:
            self.state.set_answer(contestant, answer)
            
    async def request_bets(self) -> None:
        """Request final jeopardy bets from all contestants"""
        if not self.state:
            logger.warning("Cannot start Final Jeopardy - no state available")
            return
            
        # Send category first
        await self.connection_manager.broadcast_message(
            self.FINAL_JEOPARDY_TOPIC,
            {"type": "category", "category": self.state.category}
        )
        
        # Request bets
        await self.connection_manager.broadcast_message(
            self.FINAL_JEOPARDY_TOPIC,
            {"type": "bet"}
        )
        
    async def request_answers(self) -> None:
        """Request answers from all contestants"""
        await self.connection_manager.broadcast_to_topic(
            self.FINAL_JEOPARDY_RESPONSES_TOPIC,
            {
                "topic": self.FINAL_JEOPARDY_RESPONSES_TOPIC,
                "payload": {"content": "answer"}
            }
        )
        
        # Start timer to show answer anyway after timeout
        asyncio.create_task(self.check_answers_after_timeout())
        
    async def check_bets_after_timeout(self) -> None:
        """Check if all bets are received after timeout"""
        await asyncio.sleep(self.COLLECTION_TIMEOUT)
        
        if not self.state.has_all_bets():
            missing = self.state.get_missing_bets()
            logger.warning(f"Did not receive all final jeopardy bets! Missing: {', '.join(missing)}")
        
        # Show clue anyway
        await self.handle_content_request("clue")
        
    async def check_answers_after_timeout(self) -> None:
        """Check if all answers are received after timeout"""
        await asyncio.sleep(self.COLLECTION_TIMEOUT)
        
        if not self.state.has_all_answers():
            missing = self.state.get_missing_answers()
            logger.warning(f"Did not receive all final jeopardy answers! Missing: {', '.join(missing)}")
        
        # Show answer anyway
        await self.handle_content_request("answer")
        
    async def get_response(self, contestant: str) -> None:
        """Get a contestant's final jeopardy response"""
        response = self.state.get_response(contestant) if self.state else None
        
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