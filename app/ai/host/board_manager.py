"""
Board generation and management for the AI host
"""

import logging
import json
import os
import time
import asyncio
import random
from typing import List, Dict, Any
from app.ai.board_generation.generator import BoardGenerator

logger = logging.getLogger(__name__)

class BoardManager:
    """Manages board generation and selection for the AI host"""
    
    def __init__(self):
        """Initialize the board manager"""
        self.game_service = None
    
    def set_game_service(self, game_service):
        """Set the game service reference"""
        self.game_service = game_service
        logger.info("Game service set for BoardManager")
    
    async def generate_board_from_preferences(self, preference_messages: List[Dict[str, str]]):
        """
        Generate a board based on user preferences.
        
        Args:
            preference_messages: List of messages containing user preferences
        """
        try:
            # Extract user preferences from messages
            user_preferences = " ".join([msg["message"] for msg in preference_messages])
            
            # Create board generator
            generator = BoardGenerator(user_input=user_preferences)
            
            # First, generate just the category names
            logger.info("Generating categories...")
            categories = await generator.generate_categories()
            logger.info(f"Generated categories: {categories}")
            
            # Generate a unique name for this game's board
            timestamp = time.strftime("%Y%m%d%H%M%S")
            board_name = f"generated_{timestamp}"
            
            # Create placeholder board data
            board_data = {
                "contestants": [
                    {"name": "Player 1", "score": 0},
                    {"name": "Player 2", "score": 0},
                    {"name": "Player 3", "score": 0}
                ],
                "categories": [],
                "final": None
            }
            
            # Save initial board with placeholders
            file_path = os.path.join("app/game_data", f"{board_name}.json")
            with open(file_path, 'w') as f:
                json.dump(board_data, f, indent=2)
            
            # Start all category generation tasks concurrently
            category_tasks = []
            for category in categories:
                task = generator.generate_questions_for_category(category)
                category_tasks.append(task)
            
            # Wait for all categories to be generated
            category_data = await asyncio.gather(*category_tasks)
            
            # Reveal categories one by one with a small delay
            for i, cat_data in enumerate(category_data):
                logger.info(f"Revealing category {i+1} of {len(categories)}: {cat_data['name']}")
                if self.game_service:
                    await self.game_service.connection_manager.broadcast_message(
                        "com.sc2ctl.jeopardy.reveal_category", 
                        {
                            "index": i,
                            "category": cat_data
                        }
                    )
                # Small delay between reveals for visual effect
                await asyncio.sleep(1.5)
            
            # Add daily doubles if requested
            daily_double_count = random.randint(1, 2)
            excludes = []
            for _ in range(daily_double_count):
                while True:
                    cat_idx = random.randint(0, 4)
                    q_idx = random.randint(1, 4)  # Skip $200 questions
                    if (cat_idx, q_idx) not in excludes:
                        category_data[cat_idx]["questions"][q_idx]["daily_double"] = True
                        excludes.append((cat_idx, q_idx))
                        break
            
            # Generate the final object
            board_data["categories"] = category_data
            board_data["final"] = await generator._generate_final_jeopardy()
            
            # Save complete board data
            with open(file_path, 'w') as f:
                json.dump(board_data, f, indent=2)
            
            # Set the board in the game service
            if self.game_service:
                await self.game_service.select_board(board_name)
            
            return board_name
            
        except Exception as e:
            logger.error(f"Error generating board: {e}")
            raise
    
    async def load_default_board(self):
        """Load the default board as a fallback"""
        try:
            logger.info("Attempting to load default board")
            
            if self.game_service:
                await self.game_service.select_board("default")
                return "default"
            else:
                logger.error("Cannot load default board - game service not available")
                return None
                
        except Exception as e:
            logger.error(f"Error loading default board: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None 