"""
Board Manager for AI Host

This module handles the generation and management of the Jeopardy game board.
"""

import logging
import json
import asyncio
import os
import time
import requests
from typing import List, Dict

logger = logging.getLogger(__name__)

class BoardManager:
    """
    Manages the generation and interaction with the Jeopardy game board.
    """
    
    def __init__(self, browser=None):
        """
        Initialize the board manager.
        
        Args:
            browser: Selenium browser instance
        """
        self.browser = browser
        self.base_url = "http://localhost:5173"
        self.api_url = "http://localhost:8000"
    
    async def generate_board_from_preferences(self, user_preferences):
        """
        Generate a game board based on player preferences.
        
        Args:
            user_preferences: String containing player preferences for categories
            
        Returns:
            The ID of the generated board, or None if generation failed
        """
        try:
            # Announce board generation
            logger.info(f"Generating board from preferences: {user_preferences}")
            
            # Signal frontend to show placeholder board with question marks
            logger.info("Sending start_board_generation signal")
            success = self._send_signal_to_frontend("start_board_generation", {})
            if not success:
                logger.error("Failed to send start_board_generation signal")
            
            # Import the board generator
            logger.info("Importing board generator")
            from app.ai.board_generation.generator import BoardGenerator
            
            # Generate the board
            logger.info("Creating board generator...")
            timestamp = time.strftime("%Y%m%d%H%M%S")
            generator = BoardGenerator(user_input=user_preferences)
            
            # First, generate just the category names
            logger.info("Generating categories...")
            categories = await generator.generate_categories()
            logger.info(f"Generated categories: {categories}")
            
            # Generate a unique name for this game's board
            board_name = f"generated_{timestamp}"
            
            # Generate questions for each category and reveal them one by one
            all_category_data = []
            for i, category in enumerate(categories):
                # Generate questions for this category
                logger.info(f"Generating questions for category: {category}")
                cat_data = await generator.generate_questions_for_category(category)
                all_category_data.append(cat_data)
                
                # Reveal this category on the frontend
                logger.info(f"Revealing category {i+1} of {len(categories)}: {category}")
                success = self._send_signal_to_frontend("reveal_category", {
                    "index": i,
                    "category": cat_data
                })
                if not success:
                    logger.error(f"Failed to send reveal_category signal for category {i}: {category}")
                
                # Small delay between reveals for visual effect
                await asyncio.sleep(1.5)
            
            # Generate the final object
            logger.info("Generating final board data object")
            board_data = {
                "contestants": [
                    {"name": "Player 1", "score": 0},
                    {"name": "Player 2", "score": 0},
                    {"name": "Player 3", "score": 0}
                ],
                "categories": all_category_data,
                "final": await generator._generate_final_jeopardy()
            }
            
            # Save the generated board
            file_path = os.path.join("app/game_data", f"{board_name}.json")
            logger.info(f"Saving board to {file_path}")
            with open(file_path, 'w') as f:
                json.dump(board_data, f, indent=2)
            
            logger.info(f"Board generated at {file_path}")
            
            # Select the generated board
            logger.info(f"Selecting board: {board_name}")
            success = self._select_board(board_name)
            if not success:
                logger.error(f"Failed to select board: {board_name}")
                return None
            
            # Mark game as ready to start
            logger.info("Sending game_ready signal")
            success = self._send_signal_to_frontend("game_ready", {"ready": True})
            if not success:
                logger.error("Failed to send game_ready signal")
            
            return board_name
            
        except Exception as e:
            logger.error(f"Error generating board from preferences: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def _send_signal_to_frontend(self, signal_type, payload=None):
        """
        Send a signal to the frontend using HTTP request to backend API.
        
        Args:
            signal_type: Type of signal to send
            payload: Optional payload data
            
        Returns:
            True if signal was sent successfully, False otherwise
        """
        if payload is None:
            payload = {}
            
        try:
            # Determine which endpoint to call based on signal type
            if signal_type == "start_board_generation":
                endpoint = f"{self.api_url}/api/board/start-generation"
                response = requests.post(endpoint, timeout=5)
            elif signal_type == "reveal_category":
                endpoint = f"{self.api_url}/api/board/reveal-category"
                response = requests.post(endpoint, json=payload, timeout=5)
            elif signal_type == "game_ready":
                # Use the game_service directly since there's no specific endpoint for this yet
                endpoint = f"{self.api_url}/api/board/start-generation"  # This also sets game_ready flag
                response = requests.post(endpoint, timeout=5)
            else:
                logger.error(f"Unknown signal type: {signal_type}")
                return False
            
            # Check response
            if response.status_code == 200:
                logger.info(f"Successfully sent {signal_type} signal via API: {response.json()}")
                
                # Take screenshot for debugging
                try:
                    from ..browser.selenium_utils import BrowserUtils
                    BrowserUtils.take_screenshot(self.browser, f"after_signal_{signal_type}")
                except Exception as e:
                    logger.error(f"Error taking screenshot: {e}")
                    
                return True
            else:
                logger.error(f"API request failed for {signal_type}: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending signal to frontend via API: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def _select_board(self, board_id):
        """
        Select a board through the backend API.
        
        Args:
            board_id: ID of the board to select
            
        Returns:
            True if successfully selected, False otherwise
        """
        try:
            # Call the API to select the board
            endpoint = f"{self.api_url}/api/board/select-board"
            payload = {"boardId": board_id}
            
            logger.info(f"Sending API request to select board: {board_id}")
            response = requests.post(endpoint, json=payload, timeout=5)
            
            if response.status_code == 200:
                logger.info(f"Successfully selected board via API: {response.json()}")
                return True
            else:
                logger.error(f"API request failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"Error selecting board via API: {e}")
            return False
    
    def _select_default_board(self):
        """
        Select a default board if dynamic generation fails.
        
        Returns:
            True if successfully selected, False otherwise
        """
        try:
            # Find available boards
            from selenium.webdriver.common.by import By
            board_options = self.browser.find_elements(By.CLASS_NAME, "board-option")
            if board_options:
                # Click the first board option
                board_options[0].click()
                logger.info("Selected default board")
                return True
            else:
                logger.error("No board options found")
                return False
        except Exception as e:
            logger.error(f"Error selecting default board: {e}")
            return False
    
    async def select_random_200_clue(self):
        """
        Select a random $200 clue to start the game.
        
        Returns:
            True if successfully selected, False otherwise
        """
        try:
            logger.info("Selecting a random $200 clue to start the game")
            
            # Try to find the board ID (based on the most recent generated board)
            board_id = None
            try:
                import os
                import glob
                
                # Look for generated board files
                board_files = glob.glob("app/game_data/generated_*.json")
                if board_files:
                    # Get the most recent file
                    latest_board = max(board_files, key=os.path.getctime)
                    board_id = os.path.basename(latest_board).replace(".json", "")
                    logger.info(f"Found most recent board ID: {board_id}")
            except Exception as e:
                logger.warning(f"Error finding board ID: {e}")
            
            # Give the board time to fully render all categories
            from selenium.webdriver.common.by import By
            from ..browser.selenium_utils import BrowserUtils
            
            attempts = 0
            max_attempts = 3
            categories_with_200 = []
            
            while attempts < max_attempts:
                # Get category elements
                category_elements = self.browser.find_elements(By.CSS_SELECTOR, ".jeopardy-board .category")
                
                # Build list of categories with $200 clues
                categories_with_200 = []
                for i, category_element in enumerate(category_elements):
                    title_element = category_element.find_element(By.CSS_SELECTOR, ".category-title")
                    category_name = title_element.text.strip()
                    
                    # Check if this category has a $200 clue
                    questions = category_element.find_elements(By.CSS_SELECTOR, ".question:not(.used)")
                    for question in questions:
                        if question.text.strip() == "$200":
                            categories_with_200.append({
                                "index": i,
                                "name": category_name
                            })
                            break
                
                if len(categories_with_200) >= 3:  # We should have at least 3 categories with $200 clues
                    logger.info(f"Found {len(categories_with_200)} categories with $200 clues after {attempts+1} attempts")
                    break
                    
                # Not enough categories with $200 clues, wait and try again
                logger.info(f"Only found {len(categories_with_200)} categories with $200 clues, waiting for board to fully populate (attempt {attempts+1}/{max_attempts})")
                attempts += 1
                await asyncio.sleep(2)  # Wait 2 seconds for more categories to load
                
                # Take screenshot for debugging
                BrowserUtils.take_screenshot(self.browser, f"waiting_for_board_{attempts}")
            
            if not categories_with_200:
                logger.warning("No categories with $200 clues available after waiting")
                return False
            
            # Select a random category
            import random
            selected_category = random.choice(categories_with_200)
            category_index = selected_category['index']
            category_name = selected_category['name']
            
            logger.info(f"Randomly selected category: {category_name} for $200 (index: {category_index})")
            
            # Use the API to select the question
            try:
                endpoint = f"{self.api_url}/api/board/select-question"
                payload = {
                    "categoryIndex": category_index,
                    "valueIndex": 0  # $200 is always the first question (index 0)
                }
                
                # Add board ID if available
                if board_id:
                    payload["boardId"] = board_id
                    logger.info(f"Including board ID in request: {board_id}")
                
                logger.info(f"Sending API request to select question: categoryIndex={category_index}, valueIndex=0")
                response = requests.post(endpoint, json=payload, timeout=5)
                
                if response.status_code == 200:
                    logger.info(f"Successfully selected question via API: {response.json()}")
                    return True
                else:
                    logger.error(f"API request failed: {response.status_code} - {response.text}")
                    return False
            except Exception as e:
                logger.error(f"Error sending API request: {e}")
                return False
            
        except Exception as e:
            logger.error(f"Error selecting random $200 clue: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False 