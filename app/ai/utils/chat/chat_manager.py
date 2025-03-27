"""
Chat Manager for AI Host

This module handles chat interactions between the AI host and players.
"""

import logging
from selenium.webdriver.common.by import By

logger = logging.getLogger(__name__)

class ChatManager:
    """
    Manages chat interactions for the AI host.
    
    Provides methods to send messages and process incoming messages from players.
    """
    
    def __init__(self, browser=None, host_name="AI Host"):
        """
        Initialize the chat manager.
        
        Args:
            browser: Selenium browser instance
            host_name: Name of the AI host
        """
        self.browser = browser
        self.host_name = host_name
    
    def send_chat_message(self, message):
        """
        Send a chat message as the AI host.
        
        Args:
            message: The message to send
            
        Returns:
            True if the message was sent successfully, False otherwise
        """
        try:
            chat_input = self.browser.find_element(By.CSS_SELECTOR, ".chat-input input")
            chat_button = self.browser.find_element(By.CSS_SELECTOR, ".chat-input button")
            
            chat_input.clear()
            chat_input.send_keys(message)
            chat_button.click()
            
            # Log with AI host identifier to make debugging easier
            logger.info(f"AI host ({self.host_name}) sent message: {message}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending chat message: {e}")
            return False
    
    def get_chat_messages(self):
        """
        Get all chat messages currently visible in the chat window.
        
        Returns:
            List of message dictionaries, each containing 'username', 'message', and 'key'
        """
        try:
            from ..browser.selenium_utils import BrowserUtils
            return BrowserUtils.get_chat_messages(self.browser)
        except Exception as e:
            logger.error(f"Error getting chat messages: {e}")
            return []
    
    def is_from_player(self, username, player_name):
        """
        Check if a username matches a player name (with flexible matching).
        
        Args:
            username: Username from chat message
            player_name: Name of the player to check against
            
        Returns:
            True if the username matches the player name, False otherwise
        """
        if not username or not player_name:
            return False
            
        username = username.lower()
        player_name = player_name.lower()
        
        return (username == player_name or
                username.startswith(player_name) or
                player_name.startswith(username) or
                username in player_name or
                player_name in username)
    
    def is_from_ai_host(self, username):
        """
        Check if a message is from the AI host itself.
        
        Args:
            username: Username from chat message
            
        Returns:
            True if the message is from the AI host, False otherwise
        """
        if not username:
            return False
            
        # Common AI host usernames
        ai_host_names = ["Anonymous", "AI Host", self.host_name]
        
        # Case-insensitive comparison
        username_lower = username.lower()
        return any(host_name.lower() == username_lower for host_name in ai_host_names)
    
    def get_new_messages(self, baseline_message_keys, from_player=None):
        """
        Get new messages since baseline was established.
        
        Args:
            baseline_message_keys: Set of message keys that existed before
            from_player: Optional player name to filter messages by
            
        Returns:
            List of new message dictionaries
        """
        try:
            current_messages = self.get_chat_messages()
            if not current_messages:
                return []
                
            # Find new messages (not in baseline)
            new_messages = []
            for message in current_messages:
                if message['key'] not in baseline_message_keys:
                    # Filter by player if requested
                    if from_player is None or self.is_from_player(message['username'], from_player):
                        new_messages.append(message)
            
            return new_messages
            
        except Exception as e:
            logger.error(f"Error getting new messages: {e}")
            return [] 