"""
Audio Manager for AI Host

This module handles text-to-speech synthesis and audio playback
for the AI host.
"""

import logging
import asyncio
import time
import os
import shutil
import requests
from collections import deque
from ..tts import TTSClient

logger = logging.getLogger(__name__)

class AudioManager:
    """
    Manages audio synthesis and playback for the AI host.
    
    Provides methods to synthesize speech and manage an audio queue
    for sequential playback.
    """
    
    def __init__(self, browser=None, api_key=None, voice_name="Timothy"):
        """
        Initialize the audio manager.
        
        Args:
            browser: Selenium browser instance
            api_key: API key for the Inworld API
            voice_name: Name of the voice to use for TTS
        """
        self.browser = browser
        self.tts_voice = voice_name
        self.tts_client = TTSClient(api_key=api_key)
        self.audio_queue = []
        self.audio_queue_processor = None
        self.is_running = False
        
        # Audio queue system
        self.audio_queue = deque()
        self.is_playing_audio = False
        self.audio_queue_task = None
    
    async def start(self):
        """Start the audio queue processor."""
        self.audio_queue_task = asyncio.create_task(self._process_audio_queue())
        logger.info("Audio queue processor started")
        return self.audio_queue_task
    
    def shutdown(self):
        """Stop the audio queue processor."""
        if self.audio_queue_task and not self.audio_queue_task.done():
            self.audio_queue_task.cancel()
            logger.info("Audio queue processor shutting down")
    
    async def synthesize_and_play_speech(self, text, wait_for_playback=False):
        """
        Generate speech for text and play it through the game interface.
        
        Args:
            text: The text to convert to speech
            wait_for_playback: Whether to wait for the audio to finish playing
        """
        try:
            logger.info(f"Converting to speech: {text}")
            audio_path = await self.tts_client.convert_text_to_speech(text, self.tts_voice)
            
            if not audio_path:
                logger.error("Failed to generate speech audio")
                return
                
            # Copy the file to the static directory where the backend can serve it
            backend_audio_path = os.path.join("app/static/audio", os.path.basename(audio_path))
            public_audio_path = os.path.join("/static/audio", os.path.basename(audio_path))
            
            # Ensure the directory exists
            os.makedirs(os.path.dirname(backend_audio_path), exist_ok=True)
            
            # Copy the file only if source and destination are different
            if os.path.abspath(audio_path) != os.path.abspath(backend_audio_path):
                shutil.copyfile(audio_path, backend_audio_path)
                logger.info(f"Copied audio file to backend static directory: {backend_audio_path}")
            
            # BUGFIX: Also copy to the frontend/public directory for direct access
            frontend_audio_path = os.path.join("app/frontend/public/audio", os.path.basename(audio_path))
            os.makedirs(os.path.dirname(frontend_audio_path), exist_ok=True)
            if os.path.abspath(audio_path) != os.path.abspath(frontend_audio_path):
                shutil.copyfile(audio_path, frontend_audio_path)
                logger.info(f"Also copied audio file to frontend public directory: {frontend_audio_path}")
            
            # Add to queue for playback through the browser
            logger.info(f"Adding audio to queue: {public_audio_path}")
            await self.queue_audio_for_playback(public_audio_path, wait_for_playback)
            
        except Exception as e:
            logger.error(f"Error synthesizing or playing speech: {e}")
    
    async def _process_audio_queue(self):
        """Process the audio queue, playing one file at a time."""
        try:
            logger.info("Audio queue processor started")
            while self.browser:  # Continue while browser is active
                # Check if there's audio in the queue
                if self.audio_queue and not self.is_playing_audio:
                    self.is_playing_audio = True
                    audio_url = self.audio_queue.popleft()
                    logger.info(f"Playing audio from queue: {audio_url}")
                    
                    # Try the backend API first
                    try:
                        response = requests.post(
                            "http://localhost:8000/api/play-audio",
                            json={"audio_url": audio_url},
                            timeout=5
                        )
                        
                        if response.status_code == 200:
                            logger.info(f"Successfully requested audio playback: {response.json()}")
                        else:
                            logger.error(f"Backend API request failed: {response.status_code}")
                            # Fallback to direct JavaScript
                            self._play_audio_fallback(audio_url)
                            
                    except Exception as e:
                        logger.error(f"Error sending audio play request: {e}")
                        self._play_audio_fallback(audio_url)
                    
                    # Estimate audio duration (rough approximation)
                    estimated_duration = 3 + (len(audio_url) / 7)  # Base 3 seconds + estimated text length
                    logger.info(f"Estimated audio duration: {estimated_duration:.1f} seconds")
                    
                    # Wait for estimated playback duration before processing next audio
                    await asyncio.sleep(estimated_duration)
                    self.is_playing_audio = False
                    
                # No audio to play, wait briefly before checking again
                await asyncio.sleep(0.1)
                
        except asyncio.CancelledError:
            logger.info("Audio queue processor was cancelled")
        except Exception as e:
            logger.error(f"Error in audio queue processor: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def _cleanup_audio_files(self, directory, max_files=5):
        """
        Keep only the most recent audio files, deleting older ones.
        
        Args:
            directory: The directory containing audio files
            max_files: Maximum number of files to keep
        """
        try:
            # Get list of audio files in the directory
            audio_files = []
            for filename in os.listdir(directory):
                if filename.startswith("question_audio_") and filename.endswith(".wav"):
                    file_path = os.path.join(directory, filename)
                    audio_files.append((file_path, os.path.getmtime(file_path)))
            
            # Sort files by modification time (newest first)
            audio_files.sort(key=lambda x: x[1], reverse=True)
            
            # Delete older files beyond the max_files limit
            for file_path, _ in audio_files[max_files:]:
                try:
                    os.remove(file_path)
                    logger.info(f"Removed old audio file: {file_path}")
                except Exception as e:
                    logger.error(f"Failed to remove audio file {file_path}: {e}")
            
        except Exception as e:
            logger.error(f"Error cleaning up audio files in {directory}: {e}")
    
    def _play_audio_fallback(self, audio_url):
        """Fallback method to play audio using JavaScript."""
        if not self.browser:
            logger.error("Cannot use audio fallback: browser not available")
            return
            
        script = f'''
            (function() {{
                console.log("Playing audio with fallback: {audio_url}");
                const audio = new Audio("{audio_url}");
                audio.play().catch(err => console.error("Error playing audio:", err));
            }})();
        '''
        self.browser.execute_script(script)
        logger.info("Used fallback JavaScript to play audio")
    
    async def queue_audio_for_playback(self, audio_url, wait_for_playback=False):
        """
        Queue an audio file for playback and optionally wait for it to complete.
        
        Args:
            audio_url: URL of the audio file to play
            wait_for_playback: Whether to wait for the audio to finish playing
            
        Returns:
            True if successfully queued, False otherwise
        """
        try:
            # Add to the queue
            self.audio_queue.append(audio_url)
            
            if wait_for_playback:
                # Get audio duration (approximately 1 second per 15 characters of text)
                # This is a rough estimate since we don't have direct access to the audio file's duration
                filename = os.path.basename(audio_url)
                estimated_duration = 1.0  # Minimum duration
                
                # Try to parse the filename to find the original text length
                if '_' in filename:
                    try:
                        # Use file size as a rough proxy for duration if we can access it
                        backend_path = os.path.join("app/static/audio", os.path.basename(audio_url))
                        if os.path.exists(backend_path):
                            file_size = os.path.getsize(backend_path)
                            # WAV files are roughly 16KB per second of audio at 16kHz mono
                            estimated_duration = max(1.0, file_size / 16000)
                    except:
                        # Default fallback duration
                        estimated_duration = 5.0
                
                logger.info(f"Estimated audio duration: {estimated_duration:.1f} seconds")
                await asyncio.sleep(estimated_duration)
                
            return True
        except Exception as e:
            logger.error(f"Error queueing audio for playback: {e}")
            return False 