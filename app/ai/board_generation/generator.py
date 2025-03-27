"""
Board Generator module for creating Jeopardy game data using LLM calls.
"""

import os
import json
import random
import logging
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime

from app.ai.utils.llm import LLMClient, LLMConfig

logger = logging.getLogger(__name__)

class BoardGenerator:
    """
    Generates Jeopardy game boards with categories and questions using LLM.
    """

    def __init__(self, output_dir: str = "app/game_data", model: str = "gpt-4o", user_input: str = ""):
        """
        Initialize the board generator.
        
        Args:
            output_dir: Directory where generated boards will be saved
            model: LLM model to use for generation
            user_input: User preferences or requests for the game content
        """
        self.output_dir = output_dir
        self.user_input = user_input
        self.llm_client = LLMClient(
            config=LLMConfig(
                model=model,
                temperature=0.7,
                max_tokens=2000,
                response_format={"type": "json_object"}
            )
        )
        os.makedirs(output_dir, exist_ok=True)
        
    async def generate_categories(self) -> List[str]:
        """
        Generate 5 diverse Jeopardy category names.
        
        Returns:
            List of 5 category names
        """
        prompt = f"""
        Generate 5 diverse, interesting categories for a Jeopardy game. 
        These should be challenging but accessible categories that could appear on the show.
        Make them diverse in topics (e.g., don't have multiple categories about the same subject).
        
        User preferences to consider: {self.user_input}
        Take these preferences into account when generating categories.
        
        Return the result as a JSON object with a "categories" attribute containing an array of strings, like this:
        {{
            "categories": ["Category 1", "Category 2", "Category 3", "Category 4", "Category 5"]
        }}
        """
        print(f"Generating categories with prompt: {prompt}")
        result = await self.llm_client.chat_with_prompt(
            prompt=prompt,
            system_prompt="You are a Jeopardy category designer, skilled at creating diverse, interesting categories."
        )
        
        try:
            response_obj = json.loads(result)
            if not isinstance(response_obj, dict) or "categories" not in response_obj:
                logger.warning("LLM response missing 'categories' attribute, using default")
                return ["History", "Science", "Literature", "Geography", "Pop Culture"]
                
            categories = response_obj["categories"]
            if not isinstance(categories, list) or len(categories) != 5:
                logger.warning("LLM didn't return 5 categories, using default")
                return ["History", "Science", "Literature", "Geography", "Pop Culture"]
            return categories
        except json.JSONDecodeError:
            logger.error(f"Failed to parse LLM response as JSON: {result}")
            return ["History", "Science", "Literature", "Geography", "Pop Culture"]
    
    async def generate_questions_for_category(self, category: str) -> Dict[str, Any]:
        """
        Generate 5 questions of increasing difficulty for a category.
        
        Args:
            category: The category name
        
        Returns:
            Dict with category object containing questions
        """
        prompt = f"""
        Create 5 Jeopardy-style clues and answers for the category "{category}".
        
        User preferences to consider: {self.user_input}
        Take these preferences into account when generating clues and answers.
        
        Requirements:
        1. The clues should increase in difficulty from 1-5
        2. Values should be 200, 400, 600, 800, and 1000 points respectively
        3. IMPORTANT: the clues MUST be factually accurate
        4. Each clue should be one or two sentences
        5. Format the answers as short phrases
        6. Each clue should have "daily_double": false and "type": "text"

        Return the result as a JSON object with the following structure:
        {{
            "category_data": {{
                "name": "{category}",
                "questions": [
                    {{
                        "clue": "Clue text goes here",
                        "answer": "Answer goes here",
                        "value": 200,
                        "daily_double": false,
                        "type": "text"
                    }},
                    ...
                ]
            }}
        }}

        Make sure your response is a valid JSON object.
        """
        
        result = await self.llm_client.chat_with_prompt(
            prompt=prompt,
            system_prompt="You are a Jeopardy question writer, skilled at creating factually accurate, progressively harder questions."
        )
        
        try:
            response_obj = json.loads(result)
            if not isinstance(response_obj, dict) or "category_data" not in response_obj:
                logger.warning(f"LLM response missing 'category_data' attribute for {category}")
                return self._create_fallback_category(category)
                
            category_data = response_obj["category_data"]
            if "name" not in category_data or "questions" not in category_data:
                logger.warning(f"LLM didn't return proper category structure for {category}")
                return self._create_fallback_category(category)
                
            # Validate questions
            questions = category_data["questions"]
            if len(questions) != 5:
                logger.warning(f"LLM didn't return 5 questions for {category}")
                questions = questions[:5] if len(questions) > 5 else questions
                while len(questions) < 5:
                    questions.append({
                        "clue": f"Placeholder clue for {category}",
                        "answer": "Placeholder answer",
                        "value": 200 * (len(questions) + 1),
                        "daily_double": False,
                        "type": "text"
                    })
                category_data["questions"] = questions
                
            # Ensure values are correct
            values = [200, 400, 600, 800, 1000]
            for i, question in enumerate(questions):
                question["value"] = values[i]
                question["daily_double"] = False
                
            return category_data
        except json.JSONDecodeError:
            logger.error(f"Failed to parse LLM response as JSON for {category}: {result}")
            return self._create_fallback_category(category)
    
    def _create_fallback_category(self, category: str) -> Dict[str, Any]:
        """Create a fallback category if LLM generation fails."""
        return {
            "name": category,
            "questions": [
                {
                    "clue": f"Easy clue about {category}",
                    "answer": f"Answer about {category}",
                    "value": 200,
                    "daily_double": False,
                    "type": "text"
                },
                {
                    "clue": f"Somewhat harder clue about {category}",
                    "answer": f"Answer about {category}",
                    "value": 400,
                    "daily_double": False,
                    "type": "text"
                },
                {
                    "clue": f"Medium difficulty clue about {category}",
                    "answer": f"Answer about {category}",
                    "value": 600,
                    "daily_double": False,
                    "type": "text"
                },
                {
                    "clue": f"Challenging clue about {category}",
                    "answer": f"Answer about {category}",
                    "value": 800,
                    "daily_double": False,
                    "type": "text"
                },
                {
                    "clue": f"Very difficult clue about {category}",
                    "answer": f"Answer about {category}",
                    "value": 1000,
                    "daily_double": False,
                    "type": "text"
                }
            ]
        }
    
    async def generate_board(self, board_name: Optional[str] = None, add_daily_doubles: bool = True) -> Dict[str, Any]:
        """
        Generate a complete Jeopardy board with 5 categories and 25 questions.
        
        Args:
            board_name: Optional name for the board file
            add_daily_doubles: Whether to add daily doubles (1-2 random questions)
        
        Returns:
            Complete board data as a dictionary
        """
        # Generate categories
        categories = await self.generate_categories()
        logger.info(f"Generated categories: {categories}")
        
        # Generate questions for each category concurrently
        category_tasks = []
        for category in categories:
            task = self.generate_questions_for_category(category)
            category_tasks.append(task)
        
        # Wait for all categories to be generated
        category_data = await asyncio.gather(*category_tasks)
        
        # Add daily doubles if requested
        if add_daily_doubles:
            # Add 1-2 daily doubles, excluding $200 questions
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
        
        # Generate Final Jeopardy
        final_jeopardy = await self._generate_final_jeopardy()
        
        # Create the full board data
        if not board_name:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            board_name = f"generated_{timestamp}"
            
        board_data = {
            "contestants": [
                {"name": "Player 1", "score": 0},
                {"name": "Player 2", "score": 0},
                {"name": "Player 3", "score": 0}
            ],
            "categories": category_data,
            "final": final_jeopardy
        }
        
        return board_data
    
    async def _generate_final_jeopardy(self) -> Dict[str, str]:
        """
        Generate a Final Jeopardy category, clue, and answer.
        
        Returns:
            Dictionary with final Jeopardy data
        """
        prompt = f"""
        Create a Final Jeopardy clue, category, and answer.
        
        User preferences to consider: {self.user_input}
        Take these preferences into account when generating the Final Jeopardy.
        
        The Final Jeopardy should be challenging but solvable.
        
        Return the result as a JSON object with the following structure:
        {{
            "final_jeopardy": {{
                "category": "Category Name",
                "clue": "Final Jeopardy clue text",
                "answer": "Correct response"
            }}
        }}
        """
        
        result = await self.llm_client.chat_with_prompt(
            prompt=prompt,
            system_prompt="You are a Jeopardy writer, skilled at creating challenging but fair Final Jeopardy questions."
        )
        
        try:
            response_obj = json.loads(result)
            if not isinstance(response_obj, dict) or "final_jeopardy" not in response_obj:
                logger.warning("LLM response missing 'final_jeopardy' attribute")
                return {
                    "category": "Final Jeopardy",
                    "clue": "This is a placeholder for the final Jeopardy clue",
                    "answer": "Placeholder answer"
                }
                
            final = response_obj["final_jeopardy"]
            required_keys = ["category", "clue", "answer"]
            if not all(key in final for key in required_keys):
                logger.warning("LLM didn't return proper Final Jeopardy structure")
                return {
                    "category": "Final Jeopardy",
                    "clue": "This is a placeholder for the final Jeopardy clue",
                    "answer": "Placeholder answer"
                }
                
            return final
        except json.JSONDecodeError:
            logger.error(f"Failed to parse LLM response as JSON for Final Jeopardy: {result}")
            return {
                "category": "Final Jeopardy",
                "clue": "This is a placeholder for the final Jeopardy clue",
                "answer": "Placeholder answer"
            }
    
    async def generate_and_save_board(self, board_name: Optional[str] = None, add_daily_doubles: bool = True, user_input: Optional[str] = None) -> str:
        """
        Generate a board and save it to a JSON file.
        
        Args:
            board_name: Optional name for the board file
            add_daily_doubles: Whether to add daily doubles
            user_input: Optional user preferences (overwrites the object's user_input if provided)
            
        Returns:
            Path to the saved JSON file
        """
        # Update user input if provided
        original_user_input = self.user_input
        if user_input is not None:
            self.user_input = user_input
            
        try:
            # Generate categories first
            categories = await self.generate_categories()
            logger.info(f"Generated categories: {categories}")
            
            if not board_name:
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
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
            file_path = os.path.join(self.output_dir, f"{board_name}.json")
            with open(file_path, 'w') as f:
                json.dump(board_data, f, indent=2)
            
            # Generate questions for each category concurrently
            category_tasks = []
            for category in categories:
                task = self.generate_questions_for_category(category)
                category_tasks.append(task)
            
            # Wait for all categories to be generated
            category_data = await asyncio.gather(*category_tasks)
            
            # Add daily doubles if requested
            if add_daily_doubles:
                # Add 1-2 daily doubles, excluding $200 questions
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
            
            # Generate Final Jeopardy
            final_jeopardy = await self._generate_final_jeopardy()
            
            # Update board data with all categories and final jeopardy
            board_data["categories"] = category_data
            board_data["final"] = final_jeopardy
            
            # Save complete board data
            with open(file_path, 'w') as f:
                json.dump(board_data, f, indent=2)
            
            logger.info(f"Board saved to {file_path}")
            return file_path
        finally:
            # Restore original user input
            if user_input is not None:
                self.user_input = original_user_input 