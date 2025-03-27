"""
Clue Processor for AI Host

This module handles the processing of clues, answers, and game interactions
related to the question-answer flow in the Jeopardy game.
"""

import logging
import json
import asyncio
import time
import requests
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from typing import List, Dict, Set, Optional

from ..browser.selenium_utils import BrowserUtils

logger = logging.getLogger(__name__)

class ClueProcessor:
    """
    Handles the processing of clues, including selection, answer evaluation,
    and managing question state.
    """
    
    def __init__(self, browser=None, game_state=None, llm_client=None, llm_config=None):
        """
        Initialize the clue processor.
        
        Args:
            browser: Selenium browser instance
            game_state: GameState instance for tracking game state
            llm_client: LLMClient for answer evaluation
            llm_config: Configuration for the LLM client
        """
        self.browser = browser
        self.game_state = game_state
        self.llm_client = llm_client
        self.llm_config = llm_config
        
        # Question state flags
        self.question_audio_played = False
        self.buzzer_enabled = False
    
    async def process_clue_selection(self, message):
        """
        Process a clue selection message from the player with control.
        
        Args:
            message: The chat message potentially containing a clue selection
            
        Returns:
            True if a valid clue was selected and opened, False otherwise
        """
        try:
            # Get available categories and clues from the board
            available_categories = self._get_available_categories()
            
            # No categories available
            if not available_categories:
                logger.warning("No available categories found on the board")
                return False
                
            logger.info(f"Available categories for selection:")
            for cat in available_categories:
                logger.info(f"  Category: {cat['name']}, Values: {cat['available_values']}")
            
            # Build context for the LLM template
            user_context = {
                "player_message": message,
                "available_categories": available_categories
            }
            
            # Log full context for debugging
            logger.info(f"Sending clue selection context to LLM: {json.dumps(user_context, indent=2)}")
            
            # Use LLM to evaluate the clue selection
            response_text = await self.llm_client.chat_with_template(
                user_template="clue_selection_prompt.j2",
                user_context=user_context,
                system_template="clue_selection_evaluation.j2",
                config=self.llm_config
            )
            
            try:
                response = json.loads(response_text)
                logger.info(f"LLM evaluated clue selection: {json.dumps(response, indent=2)}")
                
                if not response.get("valid", False):
                    error_msg = response.get('error', 'Unknown error')
                    logger.info(f"Invalid clue selection: {error_msg}")
                    return False
                    
                # Get the category and value
                category_name = response.get("category")
                value = response.get("value")
                
                if not category_name or not value:
                    logger.warning("Category or value missing from LLM response")
                    return False
                    
                logger.info(f"Valid clue selection: {category_name} for ${value}")
                
                # Find and click the clue on the board
                return await self._select_clue_on_board(category_name, value)
                
            except json.JSONDecodeError:
                logger.error(f"Failed to parse LLM response as JSON: {response_text}")
                return False
                
        except Exception as e:
            logger.error(f"Error processing clue selection: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def _get_available_categories(self):
        """
        Get available categories and clues from the board.
        
        Returns:
            List of dictionaries containing category name and available values
        """
        try:
            available_categories = []
            
            # Find all category elements
            category_elements = self.browser.find_elements(By.CSS_SELECTOR, ".jeopardy-board .category")
            
            for category_element in category_elements:
                # Get the category title
                title_element = category_element.find_element(By.CSS_SELECTOR, ".category-title")
                category_name = title_element.text.strip()
                if not category_name:
                    continue
                
                logger.info(f"Found category: {category_name}")
                
                # Get all clues that are not used
                available_values = []
                
                # Use direct selenium queries to find all questions that don't have the "used" class
                question_elements = category_element.find_elements(By.CSS_SELECTOR, ".question:not(.used)")
                
                for question_element in question_elements:
                    value_text = question_element.text.strip()
                    # Extract numeric value (remove $ and commas)
                    value_str = value_text.replace("$", "").replace(",", "")
                    try:
                        value = int(value_str)
                        available_values.append(value)
                        logger.info(f"  Available clue: ${value}")
                    except ValueError:
                        logger.warning(f"  Couldn't parse value from '{value_text}'")
                
                if available_values:
                    available_categories.append({
                        "name": category_name,
                        "available_values": available_values
                    })
            
            logger.info(f"Found {len(available_categories)} categories with available clues")
            return available_categories
            
        except Exception as e:
            logger.error(f"Error getting available categories: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    async def _select_clue_on_board(self, category_name, value):
        """
        Select and click a clue on the board.
        
        Args:
            category_name: The name of the category
            value: The dollar value of the clue
            
        Returns:
            True if successfully selected, False otherwise
        """
        try:
            logger.info(f"Selecting clue: {category_name} for ${value}")
            
            # Format value for matching (add $ and commas for larger values)
            value_text = f"${value:,}" if value >= 1000 else f"${value}"
            
            # Take screenshot before attempting to click
            BrowserUtils.take_screenshot(self.browser, "before_select_clue")
            
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
            
            # First find the category div that contains our target category title
            category_elements = self.browser.find_elements(By.CSS_SELECTOR, ".jeopardy-board .category")
            target_category = None
            category_index = -1
            
            # Loop through all categories to find the matching one
            for i, category_element in enumerate(category_elements):
                title_element = category_element.find_element(By.CSS_SELECTOR, ".category-title")
                current_category_name = title_element.text.strip()
                
                # Check if this is our target category (case-insensitive and contains comparison)
                if (current_category_name.lower() == category_name.lower() or 
                    category_name.lower() in current_category_name.lower() or
                    current_category_name.lower() in category_name.lower()):
                    target_category = category_element
                    category_index = i
                    logger.info(f"Found matching category: {current_category_name} at index {category_index}")
                    break
            
            if not target_category:
                logger.warning(f"Category '{category_name}' not found on the board")
                return False
            
            # Now look for the specific clue value in this category
            clues = target_category.find_elements(By.CSS_SELECTOR, ".question:not(.used)")
            target_clue = None
            value_index = -1
            
            # Map dollar values to their typically expected indices
            value_to_index = {200: 0, 400: 1, 600: 2, 800: 3, 1000: 4}
            expected_value_index = value_to_index.get(value, -1)
            
            for i, clue in enumerate(clues):
                clue_text = clue.text.strip()
                logger.info(f"Checking clue text: '{clue_text}' against target: '{value_text}'")
                
                if clue_text == value_text:
                    target_clue = clue
                    value_index = i
                    logger.info(f"Found matching clue: {clue_text} at index {value_index}")
                    break
            
            if not target_clue:
                logger.warning(f"No available ${value} clue found in category '{category_name}'")
                return False
                
            # Use the backend API to select the question
            logger.info(f"Using backend API to select question (c:{category_index}, v:{value_index}, board:{board_id})")
            
            # Send HTTP request to backend API to select the question
            try:
                endpoint = "http://localhost:8000/api/board/select-question"
                payload = {
                    "categoryIndex": category_index,
                    "valueIndex": value_index
                }
                
                # Add board ID if available
                if board_id:
                    payload["boardId"] = board_id
                
                response = requests.post(endpoint, json=payload, timeout=5)
                
                if response.status_code == 200:
                    logger.info(f"Successfully selected question via API: {response.json()}")
                    # No need to click the clue, the API has handled it
                    BrowserUtils.take_screenshot(self.browser, "after_api_select")
                    return True
                else:
                    logger.error(f"API request failed: {response.status_code} - {response.text}")
            except Exception as e:
                logger.error(f"Error sending API request: {e}")
                # If API fails, fall back to clicking
                logger.warning("API request failed, falling back to direct click")
            
            # Click the clue as a fallback if API didn't work
            logger.info("Clicking on clue element as fallback")
            
            # Wait a moment before clicking to ensure UI is stable
            await asyncio.sleep(0.5)
            
            # Scroll to make sure the clue is visible
            self.browser.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_clue)
            await asyncio.sleep(0.5)  # Give time for scrolling
            
            # Click the clue
            self.browser.execute_script("arguments[0].click();", target_clue)
            
            # Take screenshot after clicking
            BrowserUtils.take_screenshot(self.browser, "after_select_clue")
            return True
                
        except Exception as e:
            logger.error(f"Error selecting clue on board: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def monitor_current_question(self):
        """
        Monitor the current question display and update state when it changes.
        
        Returns:
            True if a new question was detected and processed, False otherwise
        """
        try:
            question_elements = self.browser.find_elements(By.CSS_SELECTOR, ".modal-content .question-text")
            if not question_elements:
                return False
                
            question_text = question_elements[0].text.strip()
            if not question_text:
                return False
                
            # If this is a new question
            if (not self.game_state.current_question or 
                self.game_state.current_question.text != question_text):
                
                logger.info(f"New question detected: {question_text}")
                
                # Reset question-related flags
                self.question_audio_played = False
                self.buzzer_enabled = False
                
                # Extract category and value
                title_elements = self.browser.find_elements(By.CSS_SELECTOR, ".modal-content h2")
                title_text = title_elements[0].text.strip() if title_elements else ""
                
                try:
                    if " - $" in title_text:
                        parts = title_text.split(" - $")
                        category = parts[0].strip()
                        value = int(parts[1].strip().replace(",", ""))
                    else:
                        category = "Unknown"
                        value = 0
                except:
                    category = "Unknown"
                    value = 0
                
                # Get correct answer if available
                correct_answer = None
                selectors = [
                    ".question-answer",
                    ".admin-controls .question-answer",
                    ".admin-controls p"
                ]
                
                for selector in selectors:
                    elements = self.browser.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        text = element.text.strip()
                        if text and not text.startswith(("Player:", "Bet:", "Player buzzed in:")):
                            correct_answer = text
                            logger.info(f"Found answer with {selector}: {correct_answer}")
                            break
                    if correct_answer:
                        break
                
                # Update game state
                self.game_state.set_question(question_text, correct_answer, category, value)
                
                # Take a screenshot for debugging
                BrowserUtils.take_screenshot(self.browser, "question_detected")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error monitoring current question: {e}")
            return False
    
    async def evaluate_answer(self, player_answer):
        """
        Use LLM to evaluate if the player's answer is correct.
        
        Args:
            player_answer: The player's answer text
            
        Returns:
            Boolean indicating if the answer is correct
        """
        if not self.game_state.current_question:
            return False
            
        question = self.game_state.current_question
        logger.info(f"Evaluating answer: '{player_answer}' against correct answer: '{question.answer}'")
        
        try:
            # Use template-based approach for the prompt
            user_context = {
                "question": question.text,
                "category": question.category,
                "correct_answer": question.answer,
                "player_answer": player_answer
            }
            
            response_text = await self.llm_client.chat_with_template(
                user_template="answer_evaluation_prompt.j2",
                user_context=user_context,
                system_template="answer_evaluation.j2",
                config=self.llm_config
            )
            
            try:
                response = json.loads(response_text)
                is_correct = response.get("correct", False)
                explanation = response.get("explanation", "No explanation provided")
                logger.info(f"LLM evaluation: correct={is_correct}, reason: {explanation}")
                return is_correct
            except json.JSONDecodeError:
                logger.error(f"Failed to parse LLM response as JSON: {response_text}")
                return False
                
        except Exception as e:
            logger.error(f"Error evaluating answer: {e}")
            return False
    
    async def mark_answer(self, is_correct):
        """
        Mark the current answer as correct or incorrect in the UI.
        
        Args:
            is_correct: Boolean indicating if the answer is correct
            
        Returns:
            True if successfully marked, False otherwise
        """
        try:
            BrowserUtils.take_screenshot(self.browser, f"before_mark_{is_correct}")
            
            # Find and click the appropriate button
            button = BrowserUtils.find_button(self.browser, is_correct)
            if button and BrowserUtils.click_button(self.browser, button):
                logger.info(f"Successfully marked answer as {'correct' if is_correct else 'incorrect'}")
                BrowserUtils.take_screenshot(self.browser, f"after_mark_{is_correct}")
                return True
            else:
                logger.warning(f"Could not find {'correct' if is_correct else 'incorrect'} button")
                return False
                
        except Exception as e:
            logger.error(f"Error marking answer: {e}")
            return False
    
    def enable_buzzer(self):
        """
        Enable the buzzer by clicking the buzzer enable button.
        
        Returns:
            True if successfully enabled, False otherwise
        """
        try:
            # Find the buzzer enable button (only if in admin mode)
            buzzer_buttons = self.browser.find_elements(By.CSS_SELECTOR, ".admin-controls .buzzer-control")
            if buzzer_buttons:
                buzzer_button = buzzer_buttons[0]
                # Check if buzzer is already active
                is_active = "active" in buzzer_button.get_attribute("class")
                
                if not is_active:
                    logger.info("Enabling buzzer for players")
                    self.browser.execute_script("arguments[0].click();", buzzer_button)
                    self.buzzer_enabled = True
                    
                    # Set current timestamp for tracking the buzzing window
                    self.game_state.set_buzzer_start_time()
                    return True
            return False
        except Exception as e:
            logger.error(f"Error enabling buzzer: {e}")
            return False
    
    async def check_question_timeout(self):
        """
        Check if the current question has timed out (no buzzer activity).
        
        Returns:
            True if question timed out and was dismissed, False otherwise
        """
        # Only check if there's an active question and no one has buzzed in
        if (not self.game_state.current_question or 
            not self.game_state.current_question.timestamp):
            return False
        
        # If a player has buzzed in, let check_for_player_answers handle timing out their answer attempt
        if self.game_state.buzzed_player:
            # Don't time out questions when a player has buzzed in and is answering
            return False
        
        # Don't start timing until the question audio has been played and buzzer is enabled
        if not self.question_audio_played or not self.buzzer_enabled:
            return False
        
        # Calculate how long the buzzer has been active without anyone buzzing in
        buzzer_age = time.time() - self.game_state.buzzer_start_time
        if buzzer_age < 7:  # Less than 7 seconds, not timed out yet
            return False
        
        logger.info(f"Question timed out after {buzzer_age:.1f} seconds with no buzzer")
        
        try:
            # Find and click the dismiss button
            dismiss_button = self.browser.find_element(By.CSS_SELECTOR, ".modal-content .dismiss")
            if dismiss_button:
                logger.info("Dismissing question due to timeout")
                
                # Store current question before dismissing
                question = self.game_state.current_question
                
                # Click dismiss button
                dismiss_button.click()
                
                # Reset question state
                self.game_state.reset_question()
                
                # Reset tracking flags
                self.question_audio_played = False
                self.buzzer_enabled = False
                
                # Save the dismissed question info to avoid repeatedly handling the same question
                if question:
                    self.game_state.add_dismissed_question(question.text)
                
                return True
            return False
        except Exception as e:
            logger.error(f"Error handling question timeout: {e}")
            return False 