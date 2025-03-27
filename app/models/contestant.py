from pydantic import BaseModel
from typing import Optional

class Contestant(BaseModel):
    name: str
    score: int = 0
    
    def add_score(self, value: int):
        self.score += value 