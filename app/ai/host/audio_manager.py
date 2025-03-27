"""
Audio management for the AI host
"""

import logging
import asyncio
import os
import time
from typing import Optional, Deque, Set
from pathlib import Path
from collections import deque

from ..utils.tts import TTSClient
from .utils.helpers import cleanup_audio_files

logger = logging.getLogger(__name__)

class AudioManager:
    """Manages audio queue and playback for the AI host"""
    
    def __init__(self, api_key=None, voice="Timothy"):
        """Initialize the audio manager"""
        self.tts_client = TTSClient(api_key=api_key)
        self.tts_voice = voice
        self.audio_queue = []
        self.is_playing_audio = False
        self.game_service = None
        self.question_audio_id = None
        self.incorrect_answer_audio_id = None
        self.recent_audio_files = set()
        self.max_recent_files = 10
        
    def set_game_service(self, game_service):
        """Set the game service reference"""
        self.game_service = game_service
        logger.info("Game service set for AudioManager")
        
    async def start(self):
        """Start the audio queue processor"""
        self.is_playing_audio = True
        asyncio.create_task(self.process_audio_queue())
        logger.info("Audio queue processor started")
        
    def shutdown(self):
        """Shut down the audio manager"""
        self.is_playing_audio = False
        logger.info("Audio manager shutting down")
        
    def is_audio_playing(self) -> bool:
        """Check if any audio is currently playing."""
        return self.question_audio_id is not None or self.incorrect_answer_audio_id is not None
        
    def clear_question_audio_id(self, audio_id: str):
        """Clear the question audio ID if it matches the completed audio ID."""
        if self.question_audio_id == audio_id:
            logger.info(f"Clearing question audio ID: {audio_id}")
            self.question_audio_id = None
            return True
        return False
        
    def clear_incorrect_answer_audio_id(self, audio_id: str):
        """Clear the incorrect answer audio ID if it matches the completed audio ID."""
        if self.incorrect_answer_audio_id == audio_id:
            logger.info(f"Clearing incorrect answer audio ID: {audio_id}")
            self.incorrect_answer_audio_id = None
            return True
        return False
        
    def check_and_clear_audio_ids(self, audio_id: str):
        """
        Check which type of audio has completed and clear the corresponding ID.
        
        Args:
            audio_id: The ID of the completed audio
            
        Returns:
            Tuple of (was_question_audio, was_incorrect_answer)
        """
        was_question = self.clear_question_audio_id(audio_id)
        was_incorrect = self.clear_incorrect_answer_audio_id(audio_id)
        return (was_question, was_incorrect)

    async def synthesize_and_play_speech(self, text: str, is_question_audio=False, is_incorrect_answer_audio=False):
        """
        Synthesize speech from text and play it to all clients.
        
        Args:
            text: The text to convert to speech
            is_question_audio: Whether this is a question being read
            is_incorrect_answer_audio: Whether this is an incorrect answer response
        """
        try:
            logger.info(f"Converting to speech: {text}")
            
            # Generate unique filename with timestamp
            timestamp = int(time.time())
            filename = f"question_audio_{timestamp}.wav"
            
            # Generate a unique audio ID that will be used to track this playback
            if is_incorrect_answer_audio:
                # Mark incorrect answer audio specially
                audio_id = f"audio_incorrect_{timestamp}"
                logger.info(f"Saved incorrect answer audio ID: {audio_id}")
            else:
                audio_id = f"audio_{timestamp}"
                logger.info(f"Saved audio ID: {audio_id}")
            
            # If this audio is for a question, track its ID
            if is_question_audio:
                self.question_audio_id = audio_id
                logger.info(f"Setting question audio ID to {self.question_audio_id}")
            
            # If this is a duplicate speech request for the same file, skip it
            if filename in self.recent_audio_files:
                logger.warning(f"Skipping duplicate speech synthesis for file: {filename}")
                return
                
            # Add to recent files set before generating to prevent race conditions
            self.recent_audio_files.add(filename)
            
            # Limit the size of recent files set
            if len(self.recent_audio_files) > 20:
                oldest_files = sorted(self.recent_audio_files)[:10]  # Sort by timestamp in filename
                self.recent_audio_files = self.recent_audio_files - set(oldest_files)
            
            # Create paths for audio files
            static_dir = os.path.join("static", "audio")
            
            # Ensure directories exist
            os.makedirs(static_dir, exist_ok=True)
            
            # Generate speech - use the correct method name from TTSClient
            output_path = os.path.join(static_dir, filename)
            result_file = self.tts_client.generate_speech(
                text=text,
                voice_name=self.tts_voice,
                output_file=output_path
            )
            
            if os.path.exists(result_file) and os.path.getsize(result_file) > 0:
                # Add to audio queue instead of playing immediately
                public_url = f"/static/audio/{filename}"
                logger.info(f"Adding audio to queue: {public_url}")
                
                # Check if this audio file is already in the queue to prevent duplicates
                if public_url not in self.audio_queue:
                    self.audio_queue.append(public_url)
                else:
                    logger.warning(f"Skipping duplicate audio in queue: {public_url}")
                
                # Clean up old audio files
                await cleanup_audio_files(static_dir, 5)
            else:
                logger.error(f"Failed to create valid audio file at: {result_file}")
            
        except Exception as e:
            logger.error(f"Error synthesizing speech: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def process_audio_queue(self):
        """Process the audio queue and play audio files"""
        while self.is_playing_audio:
            try:
                # Sleep briefly to avoid tight polling
                await asyncio.sleep(0.5)
                
                # Skip if the queue is empty
                if not self.audio_queue:
                    continue
                
                # Get the next audio file from the queue
                audio_url = self.audio_queue.pop(0) if self.audio_queue else None
                if not audio_url:
                    continue
                
                logger.info(f"Processing audio from queue: {audio_url}")
                
                # If game service is available, use it to play the audio
                if self.game_service:
                    # Use unique audio ID to track completion
                    audio_id = f"audio_{int(time.time() * 1000)}"
                    
                    # Play the audio through the game service
                    await self.game_service.play_audio(
                        audio_url=audio_url,
                        wait_for_completion=True,
                        audio_id=audio_id
                    )
                    
                    # Wait for the audio to complete - timeout after 30 seconds
                    max_wait_time = 30
                    wait_time = 0
                    while wait_time < max_wait_time:
                        # Check if audio playback has completed
                        if self.game_service.check_audio_completed(audio_id):
                            logger.info(f"Audio playback completed: {audio_id}")
                            break
                            
                        # Wait a bit before checking again
                        await asyncio.sleep(1)
                        wait_time += 1
                        
                    if wait_time >= max_wait_time:
                        logger.warning(f"Timed out waiting for audio completion: {audio_id}")
                else:
                    # No game service available - just simulate delay based on URL length
                    # This is a rough estimate based on human speech rate
                    await asyncio.sleep(5)  # Default delay
                    logger.info("No game service - simulated audio playback")
                    
            except Exception as e:
                logger.error(f"Error processing audio queue: {e}")
                import traceback
                logger.error(traceback.format_exc())