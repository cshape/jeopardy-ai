"""
Text-to-Speech client using Inworld's TTS API.
This module provides a class for generating speech from text.
"""

import requests
import json
import base64
import os
import logging
from pathlib import Path

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class TTSClient:
    """
    Client for Inworld's speech-to-text service.
    
    This class provides methods to convert text to speech using Inworld's TTS API.
    """
    
    def __init__(self, api_key=None):
        """
        Initialize the TTS client.
        
        Args:
            api_key (str, optional): The Inworld API key. If not provided, it will
                                     attempt to load from INWORLD_API_KEY environment variable.
        
        Raises:
            ValueError: If API key is not provided and not found in environment variables.
        """
        self.api_key = api_key or os.environ.get("INWORLD_API_KEY")
        
        if not self.api_key:
            raise ValueError(
                "API key is required. Either pass it to the constructor or "
                "set the INWORLD_API_KEY environment variable."
            )
        
        # Use the non-sync endpoint as in the documentation
        self.url = 'https://api.inworld.ai/tts/v1alpha/text:synthesize-sync'
        
        # Make sure the Authorization header is properly formatted
        # The API key might already include "Basic " prefix or might need it added
        auth_value = self.api_key
        if not auth_value.startswith("Basic "):
            auth_value = f"Basic {auth_value}"
            
        self.headers = {
            'Authorization': auth_value,
            'Content-Type': 'application/json'
        }
        logger.info(f"Initialized TTSClient with API URL: {self.url}")
    
    def generate_speech(self, text, voice_name="Timothy", output_file=None):
        """
        Generate speech from text and save it to a WAV file.
        
        Args:
            text (str): The text to convert to speech.
            voice_name (str, optional): The name of the voice to use. Defaults to "Timothy".
            output_file (str, optional): Path to save the WAV file. If not provided,
                                        a temporary file will be created.
        
        Returns:
            str: The path to the generated WAV file.
            
        Raises:
            Exception: If the API request fails.
        """
        logger.info(f"Generating speech for text: '{text[:50]}...' with voice: {voice_name}")
        
        payload = {
            'input': {
                'text': text
            },
            'voice': {
                'name': voice_name
            },
            'audio_config': {
                'audio_encoding': 'LINEAR16'  # Ensure we get WAV format
            }
        }
        
        try:
            logger.info(f"Making API request to {self.url}")
            
            response = requests.post(
                self.url,
                headers=self.headers,
                data=json.dumps(payload),
                timeout=30
            )
            
            logger.info(f"API response status code: {response.status_code}")
            
            # Check if the response is successful
            if response.status_code != 200:
                logger.error(f"API error: {response.status_code} - {response.text}")
                raise Exception(f"API returned error: {response.status_code} - {response.text}")
            
            # Create a file path if not provided
            if not output_file:
                # Create a temporary file name with the first few words of the text
                text_preview = text[:20].replace(" ", "_").replace("/", "_")
                output_file = f"tts_{text_preview}.wav"
            
            # Ensure the directory exists
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Extract and process audio content
            try:
                # Try to extract the base64 audio content using string operations
                # This is more robust than JSON parsing if the response is malformed
                response_text = response.text
                
                # Look for the audioContent field
                if '"audioContent":"' in response_text:
                    logger.info("Found audioContent field in response")
                    
                    # Find the start and end of the base64 content
                    start_marker = '"audioContent":"'
                    start_pos = response_text.find(start_marker) + len(start_marker)
                    end_pos = response_text.find('"', start_pos)
                    
                    if end_pos > start_pos:
                        # Extract the base64 string
                        audio_base64 = response_text[start_pos:end_pos]
                        
                        # Decode the base64 data
                        audio_data = base64.b64decode(audio_base64)
                        
                        # Write to file
                        with open(output_file, 'wb') as f:
                            f.write(audio_data)
                        
                        logger.info(f"Successfully saved decoded audio to: {output_file}")
                        return output_file
                
                # Fallback to using JSON parsing if the string approach didn't work
                logger.info("Trying JSON parsing as fallback")
                try:
                    # Only parse the first JSON object if there are multiple
                    json_str = response_text.split('\n')[0]
                    data = json.loads(json_str)
                    
                    if 'result' in data and 'audioContent' in data['result']:
                        audio_base64 = data['result']['audioContent']
                        audio_data = base64.b64decode(audio_base64)
                        
                        with open(output_file, 'wb') as f:
                            f.write(audio_data)
                        
                        logger.info(f"Successfully saved audio via JSON parsing to: {output_file}")
                        return output_file
                except json.JSONDecodeError:
                    logger.warning("JSON parsing fallback also failed")
                
                # Last resort: save raw response
                logger.warning("Using raw response as last resort")
                with open(output_file, 'wb') as f:
                    f.write(response.content)
                
                logger.info(f"Saved raw response to: {output_file}")
                return output_file
                
            except Exception as e:
                logger.error(f"Error processing response: {e}")
                # Save raw response as fallback
                with open(output_file, 'wb') as f:
                    f.write(response.content)
                logger.info(f"Saved raw response after error: {output_file}")
                return output_file
            
        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP request error: {str(e)}")
            raise Exception(f"Failed to make API request: {str(e)}")
        except Exception as e:
            logger.error(f"Error generating speech: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            raise Exception(f"Failed to generate speech: {str(e)}") 