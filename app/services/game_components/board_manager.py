import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class BoardManager:
    def __init__(self, boards_path: Path):
        self.boards_path = boards_path
        self.current_board = None
        
    async def load_board(self, board_id: str) -> Dict[str, Any]:
        """Load a board from the filesystem"""
        try:
            board_path = self.boards_path / f"{board_id}.json"
            if not board_path.exists():
                raise FileNotFoundError(f"Board {board_id} not found")

            with open(board_path, 'r') as f:
                board_data = json.load(f)
                return board_data

        except Exception as e:
            logger.error(f"Error loading board {board_id}: {e}")
            raise
            
    def find_question(self, category_name: str, value: int) -> Optional[Dict[str, Any]]:
        """Find a question in the current board"""
        if not self.current_board or "categories" not in self.current_board:
            return None

        for category in self.current_board["categories"]:
            if category["name"] == category_name:
                for question in category["questions"]:
                    if question["value"] == value:
                        return question
        return None

    def mark_question_used(self, category_name: str, value: int) -> None:
        """Mark a question as used"""
        if not self.current_board or "categories" not in self.current_board:
            return

        for category in self.current_board["categories"]:
            if category["name"] == category_name:
                for question in category["questions"]:
                    if question["value"] == value:
                        question["used"] = True
                        break
                        
    def all_questions_answered(self) -> bool:
        """Check if all questions have been answered"""
        if not self.current_board or "categories" not in self.current_board:
            return False
            
        for category in self.current_board["categories"]:
            for question in category["questions"]:
                if not question.get("used", False):
                    return False
        return True 