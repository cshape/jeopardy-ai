import unittest
import time
import os
import subprocess
import signal
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementNotVisibleException, ElementClickInterceptedException

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('JeopardyE2ETest')


class JeopardyE2ETest(unittest.TestCase):
    """End-to-end tests for the Jeopardy app using Selenium."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment once before all tests."""
        try:
            logger.info("Setting up test environment...")
            # Start the app server if needed
            # This is equivalent to setupTestEnvironment in the JS version
            # Uncomment if you need to start the server as part of the test
            # cls.server_process = subprocess.Popen(['python', '-m', 'app.main'])
            # time.sleep(2)  # Give the server time to start
            
            # Configure browser options
            cls.admin_options = webdriver.ChromeOptions()
            cls.admin_options.add_argument('--headless')
            cls.admin_options.add_argument('--window-size=1280,800')
            
            # Create admin browser
            logger.info("Creating admin browser...")
            cls.admin_browser = webdriver.Chrome(options=cls.admin_options)
            cls.admin_browser.set_window_size(1280, 800)
            
            # Create player browsers
            logger.info("Creating player browsers...")
            cls.player_browsers = []
            for i in range(3):
                options = webdriver.ChromeOptions()
                options.add_argument('--headless')
                options.add_argument('--window-size=1280,800')
                browser = webdriver.Chrome(options=options)
                browser.set_window_size(1280, 800)
                cls.player_browsers.append(browser)
            logger.info("Test setup completed successfully")
        except Exception as e:
            logger.error(f"Error in setUpClass: {e}")
            raise
    
    @classmethod
    def tearDownClass(cls):
        """Clean up after all tests have run."""
        logger.info("Cleaning up test environment...")
        # Close all browser instances
        try:
            cls.admin_browser.quit()
            for browser in cls.player_browsers:
                browser.quit()
                
            # Kill any remaining server processes if needed
            try:
                subprocess.run(['pkill', '-f', 'python -m app.main'], check=False)
                logger.info('Killed server processes')
            except Exception:
                logger.info('No server processes to kill')
            
            logger.info("Test cleanup completed successfully")
        except Exception as e:
            logger.error(f"Error in tearDownClass: {e}")
    
    def setUp(self):
        """Set up before each test."""
        logger.info(f"Starting test: {self._testMethodName}")
    
    def tearDown(self):
        """Clean up after each test."""
        logger.info(f"Completed test: {self._testMethodName}")
    
    def test_01_admin_can_select_board_and_players_can_join(self):
        """Test that admin can select a board and players can join the game."""
        # 1. Admin opens the app and selects a board
        logger.info('Admin navigating to app with admin mode...')
        self.admin_browser.get('http://localhost:5173/?admin=true')
        
        # Wait for board selector to appear
        WebDriverWait(self.admin_browser, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, 'board-selector'))
        )
        
        # Select the first board
        board_options = self.admin_browser.find_elements(By.CLASS_NAME, 'board-option')
        self.assertTrue(len(board_options) > 0, "No board options found")
        
        logger.info('Admin selecting a board...')
        board_options[0].click()
        
        # Wait for the board to load
        WebDriverWait(self.admin_browser, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, 'jeopardy-board'))
        )
        
        # Verify that categories are displayed
        categories = self.admin_browser.find_elements(By.CLASS_NAME, 'category-title')
        self.assertTrue(len(categories) > 0)
        logger.info(f'Admin sees {len(categories)} categories')
        
        # 2. Players join one by one
        logger.info('Players joining...')
        
        # First player joins
        logger.info('Player 1 joining...')
        self.player_browsers[0].get('http://localhost:5173')
        
        # Enter player 1 name and submit
        WebDriverWait(self.player_browsers[0], 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="text"]'))
        ).send_keys('Player 1')
        
        self.player_browsers[0].find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
        
        # Verify player 1 entered waiting state
        WebDriverWait(self.player_browsers[0], 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, 'waiting-screen'))
        )
        
        # Second player joins
        logger.info('Player 2 joining...')
        self.player_browsers[1].get('http://localhost:5173')
        WebDriverWait(self.player_browsers[1], 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="text"]'))
        ).send_keys('Player 2')
        
        self.player_browsers[1].find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
        
        # Verify player 2 entered waiting state
        WebDriverWait(self.player_browsers[1], 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, 'waiting-screen'))
        )
        
        # Verify that both players see each other in the waiting room
        player1_names = [el.text for el in self.player_browsers[0].find_elements(By.CSS_SELECTOR, '.current-players li')]
        
        self.assertIn('Player 1', player1_names)
        self.assertIn('Player 2', player1_names)
        
        # Third player joins (this should start the game)
        logger.info('Player 3 joining...')
        self.player_browsers[2].get('http://localhost:5173')
        WebDriverWait(self.player_browsers[2], 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="text"]'))
        ).send_keys('Player 3')
        
        self.player_browsers[2].find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
        
        # Wait for the game to start for all players
        logger.info('Waiting for game board to appear for all players...')
        
        # Wait for all players to see the game board
        for i, browser in enumerate(self.player_browsers):
            WebDriverWait(browser, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, 'jeopardy-board'))
            )
            
            # Verify that all players see the game board
            categories = browser.find_elements(By.CLASS_NAME, 'category-title')
            self.assertTrue(len(categories) > 0)
            logger.info(f'Player {i+1} sees {len(categories)} categories')
            
            # Verify that all players are shown in the scoreboard
            player_scores = browser.find_elements(By.CLASS_NAME, 'player-score')
            self.assertEqual(len(player_scores), 3)
            
            player_names = [el.text for el in browser.find_elements(By.CLASS_NAME, 'player-name')]
            
            self.assertIn('Player 1', player_names)
            self.assertIn('Player 2', player_names)
            self.assertIn('Player 3', player_names)
        
        logger.info('Test completed successfully!')
    
    def test_02_admin_shows_question_players_see_it_and_admin_dismisses_it(self):
        """Test that admin can select a question, players see it, and admin can dismiss it."""
        # Admin selects a question
        logger.info('Admin selecting a question...')
        question_cells = self.admin_browser.find_elements(By.CLASS_NAME, 'question')
        question_cells[0].click()

        # Wait for question modal to appear
        WebDriverWait(self.admin_browser, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, 'modal-content'))
        )
        
        # Verify all players see the question
        for i, browser in enumerate(self.player_browsers):
            WebDriverWait(browser, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, 'modal-content'))
            )
            logger.info(f'Player {i+1} sees the question')

        # Admin dismisses the question
        logger.info('Admin dismissing question...')
        self.admin_browser.find_element(By.CLASS_NAME, 'dismiss').click()

        # Verify admin no longer sees the modal
        WebDriverWait(self.admin_browser, 10).until(
            EC.invisibility_of_element_located((By.CLASS_NAME, 'modal-content'))
        )
        logger.info('Question dismissed by admin')
        
        # Verify all players no longer see the modal
        for i, browser in enumerate(self.player_browsers):
            WebDriverWait(browser, 10).until(
                EC.invisibility_of_element_located((By.CLASS_NAME, 'modal-content'))
            )
            logger.info(f'Player {i+1} no longer sees the question')
    
    def test_03_player_buzzes_in_admin_marks_answer_as_incorrect(self):
        """Test that a player can buzz in and admin can mark the answer as incorrect."""
        # Admin selects a question
        logger.info('Admin selecting a question...')
        question_cells = self.admin_browser.find_elements(By.CLASS_NAME, 'question')
        question_cells[1].click()

        # Wait for question modal to appear
        WebDriverWait(self.admin_browser, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, 'modal-content'))
        )
        
        # Player 1 buzzes in
        logger.info('Player 1 buzzing in...')
        self.player_browsers[0].find_element(By.CLASS_NAME, 'player-buzzer').click()
        
        # Wait for admin to see the buzz
        WebDriverWait(self.admin_browser, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '.admin-controls p'))
        )
        
        # Verify admin sees the buzz
        buzzed_in_text = self.admin_browser.find_element(By.CSS_SELECTOR, '.admin-controls p').text
        self.assertIn('Player 1', buzzed_in_text)
        logger.info('Admin sees Player 1 has buzzed in')
        
        # Admin marks answer as incorrect
        logger.info('Admin marking answer as incorrect...')
        self.admin_browser.find_element(By.CLASS_NAME, 'incorrect').click()
        
        # Verify modal closes
        WebDriverWait(self.admin_browser, 10).until(
            EC.invisibility_of_element_located((By.CLASS_NAME, 'modal-content'))
        )

        # Verify player sees the result
        WebDriverWait(self.player_browsers[0], 10).until(
            EC.invisibility_of_element_located((By.CLASS_NAME, 'modal-content'))
        )

        # Verify Player 1's score has decreased
        # Find the player-score element that contains "Player 1"
        player_scores = self.player_browsers[0].find_elements(By.CLASS_NAME, 'player-score')
        player1_score = None
        for element in player_scores:
            player_name = element.find_element(By.CLASS_NAME, 'player-name').text
            if 'Player 1' in player_name:
                score_text = element.find_element(By.CLASS_NAME, 'score').text
                player1_score = int(score_text.replace('$', ''))
                break
        
        self.assertIsNotNone(player1_score)
        self.assertLess(player1_score, 0)
        logger.info(f'Player 1 score decreased to {player1_score}')
    
    def test_04_player_buzzes_in_admin_marks_answer_as_correct(self):
        """Test that a player can buzz in and admin can mark the answer as correct."""
        # Admin selects a question
        logger.info('Admin selecting a question...')
        question_cells = self.admin_browser.find_elements(By.CLASS_NAME, 'question')
        question_cells[2].click()

        # Wait for question modal to appear
        WebDriverWait(self.admin_browser, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, 'modal-content'))
        )

        # Player 2 buzzes in
        logger.info('Player 2 buzzing in...')
        self.player_browsers[1].find_element(By.CLASS_NAME, 'player-buzzer').click()
        
        # Wait for admin to see the buzz
        WebDriverWait(self.admin_browser, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '.admin-controls p'))
        )

        # Verify admin sees the buzz
        buzzed_in_text = self.admin_browser.find_element(By.CSS_SELECTOR, '.admin-controls p').text
        self.assertIn('Player 2', buzzed_in_text)
        logger.info('Admin sees Player 2 has buzzed in')
        
        # Admin marks answer as correct
        logger.info('Admin marking answer as correct...')
        self.admin_browser.find_element(By.CLASS_NAME, 'correct').click()
        
        # Verify modal closes
        WebDriverWait(self.admin_browser, 10).until(
            EC.invisibility_of_element_located((By.CLASS_NAME, 'modal-content'))
        )

        # Verify player sees the result
        WebDriverWait(self.player_browsers[1], 10).until(
            EC.invisibility_of_element_located((By.CLASS_NAME, 'modal-content'))
        )

        # Verify Player 2's score has increased
        # Find the player-score element that contains "Player 2"
        player_scores = self.player_browsers[1].find_elements(By.CLASS_NAME, 'player-score')
        player2_score = None
        for element in player_scores:
            player_name = element.find_element(By.CLASS_NAME, 'player-name').text
            if 'Player 2' in player_name:
                score_text = element.find_element(By.CLASS_NAME, 'score').text
                player2_score = int(score_text.replace('$', ''))
                break
        
        self.assertIsNotNone(player2_score)
        self.assertGreater(player2_score, 0)
        logger.info(f'Player 2 score increased to {player2_score}')
    
    def test_05_player_encounters_daily_double(self):
        """Test that a player can encounter a daily double."""
        logger.info('Admin searching for a daily double question...')
        
        # Get all questions
        all_questions = self.admin_browser.find_elements(By.CLASS_NAME, 'question')
        logger.info(f'Found {len(all_questions)} total questions')
        all_questions[14].click()

        # Wait for question modal to appear
        WebDriverWait(self.admin_browser, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, 'modal-content'))
        )
        if (self.admin_browser.find_element(By.CLASS_NAME, 'modal-content.daily-double')):
            logger.info("Daily double found successfully")
        else:
            logger.error("Could not find any daily double question")
            self.fail("Could not find any daily double question")



if __name__ == '__main__':
    unittest.main() 