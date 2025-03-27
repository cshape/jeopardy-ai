from typing import Dict, Optional, List
from pydantic import BaseModel

class GameStateManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GameStateManager, cls).__new__(cls)
            cls._instance.initialize()
        return cls._instance
    
    def initialize(self):
        self.contestants: Dict[str, 'Contestant'] = {}  # websocket_id -> Contestant
        self.current_question = None
        self.buzzer_active = False
        self.last_buzzer = None
        self.used_questions = set()  # Track used questions
        
    def register_contestant(self, websocket_id: str, name: str) -> bool:
        """Register a new contestant if name is available"""
        if any(c.name == name for c in self.contestants.values()):
            return False
        
        from ..models.contestant import Contestant
        self.contestants[websocket_id] = Contestant(name=name, score=0)
        return True
    
    def get_contestant_by_websocket(self, websocket_id: str) -> Optional['Contestant']:
        return self.contestants.get(websocket_id)
    
    def remove_contestant(self, websocket_id: str):
        if websocket_id in self.contestants:
            del self.contestants[websocket_id] 
    
    def get_game_state(self) -> dict:
        """Get current game state for new connections"""
        return {
            "contestants": {
                name: {"score": contestant.score}
                for name, contestant in self.contestants.items()
            },
            "current_question": self.current_question,
            "buzzer_active": self.buzzer_active,
            "last_buzzer": self.last_buzzer,
            "used_questions": list(self.used_questions)
        } 