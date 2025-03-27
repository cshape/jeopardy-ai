"""
Command-line interface for generating Jeopardy boards.
"""

import os
import argparse
import asyncio
import logging
from datetime import datetime

from app.ai.board_generation.generator import BoardGenerator

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def main():
    """Run the board generation CLI."""
    parser = argparse.ArgumentParser(description='Generate Jeopardy game boards')
    parser.add_argument('--name', type=str, help='Name for the board file')
    parser.add_argument('--count', type=int, default=1, help='Number of boards to generate')
    parser.add_argument('--output-dir', type=str, default='app/game_data', help='Output directory')
    parser.add_argument('--model', type=str, default='gpt-4o-mini', help='LLM model to use')
    parser.add_argument('--no-daily-doubles', action='store_true', help='Disable daily doubles')
    parser.add_argument('--user-input', type=str, default='', 
                      help='User preferences for the game (e.g., "nothing about science", "make it super easy")')
    
    args = parser.parse_args()
    
    generator = BoardGenerator(
        output_dir=args.output_dir,
        model=args.model,
        user_input=args.user_input
    )
    
    for i in range(args.count):
        if args.count > 1:
            if args.name:
                board_name = f"{args.name}_{i+1}"
            else:
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                board_name = f"generated_{timestamp}_{i+1}"
        else:
            board_name = args.name
        
        file_path = await generator.generate_and_save_board(
            board_name=board_name,
            add_daily_doubles=not args.no_daily_doubles
        )
        
        print(f"Generated board saved to: {file_path}")

if __name__ == "__main__":
    asyncio.run(main()) 