import logging
from typing import Dict, Any, Optional, List
from fastapi import WebSocket
from ..websockets.connection_manager import ConnectionManager
from ..models.contestant import Contestant

logger = logging.getLogger(__name__)

class ContestantManager:
    CONTESTANT_SCORE_TOPIC = "com.sc2ctl.jeopardy.contestant_score"
    REQUIRED_PLAYERS = 3
    
    def __init__(self, connection_manager: ConnectionManager):
        self.connection_manager = connection_manager
        self.contestants: Dict[str, Contestant] = {}
        self.game_ready = False
        self.last_correct_contestant = None
        
    def get_contestant_by_websocket(self, websocket_id: str) -> Optional[Contestant]:
        """Get a contestant by their websocket ID"""
        return self.contestants.get(websocket_id)
        
    def find_contestant(self, name: str) -> Optional[Contestant]:
        """Find a contestant by name"""
        for contestant in self.contestants.values():
            if contestant.name == name:
                return contestant
        return None
        
    async def register_player(self, websocket: WebSocket, name: str) -> bool:
        """Register a new player with the given name"""
        websocket_id = str(id(websocket))
        
        # Check if name is already taken
        for contestant in self.contestants.values():
            if contestant.name == name:
                return False
                
        # Add new contestant
        self.contestants[websocket_id] = Contestant(name=name)
        
        # Broadcast updated player list
        await self.broadcast_player_list()
        
        # Check if we have enough players
        if len(self.contestants) >= self.REQUIRED_PLAYERS:
            self.game_ready = True
            await self.connection_manager.broadcast_message(
                "com.sc2ctl.jeopardy.game_ready",
                {"ready": True}
            )
            
        return True
        
    async def broadcast_player_list(self) -> None:
        """Send current player list to all clients"""
        players = {
            c.name: {"score": c.score} 
            for c in self.contestants.values()
        }
        await self.connection_manager.broadcast_message(
            "com.sc2ctl.jeopardy.player_list",
            {"players": players}
        )
        
    async def update_score(self, contestant_name: str, score_delta: int) -> None:
        """Update a contestant's score"""
        contestant = self.find_contestant(contestant_name)
        if contestant:
            contestant.score += score_delta
            await self.broadcast_scores()
            
    async def broadcast_scores(self) -> None:
        """Send current contestant scores to all clients"""
        scores = {
            contestant.name: contestant.score 
            for contestant in self.contestants.values()
        }
        await self.connection_manager.broadcast_message(
            self.CONTESTANT_SCORE_TOPIC,
            {"scores": scores}
        ) 