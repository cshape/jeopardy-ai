import logging
import asyncio
from typing import Set, Optional
from fastapi import WebSocket
from ..websockets.connection_manager import ConnectionManager

logger = logging.getLogger(__name__)

class BuzzerManager:
    BUZZER_TOPIC = "com.sc2ctl.jeopardy.buzzer"
    BUZZER_STATUS_TOPIC = "com.sc2ctl.jeopardy.buzzer_status"
    BUZZER_RESOLVE_TIMEOUT = 0.75  # seconds

    def __init__(self, connection_manager: ConnectionManager):
        self.connection_manager = connection_manager
        self.active = False
        self.last_buzzer = None
        self.buzzed_contestants: Set[str] = set()
        
    def clear_state(self) -> None:
        """Clear buzzer state"""
        self.active = False
        self.last_buzzer = None
        self.buzzed_contestants.clear()
        
    async def handle_buzz(self, websocket: WebSocket, contestant_name: str, timestamp: float) -> bool:
        """Handle a buzz from a contestant"""
        if not self.active:
            logger.warning(f"Buzz from {contestant_name} ignored - buzzer not active")
            return False
            
        if contestant_name in self.buzzed_contestants:
            logger.warning(f"Contestant {contestant_name} already buzzed for this question")
            return False
            
        logger.info(f"Buzz accepted from {contestant_name}")
        self.buzzed_contestants.add(contestant_name)
        self.last_buzzer = contestant_name
        
        # Deactivate buzzer when someone successfully buzzes in
        await self.change_status(False)
        
        # Notify all clients of the buzz
        await self.connection_manager.broadcast_message(
            self.BUZZER_TOPIC,
            {"contestant": contestant_name, "timestamp": timestamp}
        )
        
        return True
        
    async def change_status(self, active: bool) -> None:
        """Change buzzer status and broadcast to all clients"""
        logger.info(f"Setting buzzer status to: {active}")
        self.active = active
        await self.connection_manager.broadcast_message(
            self.BUZZER_STATUS_TOPIC,
            {"active": active}
        )
        
    async def resolve_buzzes_after_timeout(self) -> None:
        """Resolve buzzes after a timeout period"""
        logger.info("Starting buzzer resolution timeout")
        await asyncio.sleep(self.BUZZER_RESOLVE_TIMEOUT)
        
        # If no contestant has buzzed in during timeout, reactivate the buzzer
        if not self.last_buzzer:
            logger.info("No buzzer during timeout - reactivating buzzer")
            await self.change_status(True)
        else:
            logger.info(f"Contestant {self.last_buzzer} buzzed in during timeout")
            
            # Notify about the contestant who buzzed in
            await self.connection_manager.broadcast_message(
                self.BUZZER_TOPIC,
                {"contestant": self.last_buzzer}
            ) 