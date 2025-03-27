from pydantic import BaseModel
from typing import Optional, Literal

class Clue(BaseModel):
    text: str
    
    def __str__(self) -> str:
        return self.text

class Answer(BaseModel):
    text: str
    
    def __str__(self) -> str:
        return self.text

class Question(BaseModel):
    clue: Clue
    answer: Answer
    value: int
    daily_double: bool = False
    type: Literal["text", "image", "audio", "video"] = "text"
    used: bool = False
    
    def mark_as_used(self):
        self.used = True
    
    def is_daily_double(self) -> bool:
        return self.daily_double 