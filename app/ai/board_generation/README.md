# Jeopardy Board Generator

This module provides LLM-powered generation of Jeopardy game boards with categories and questions.

## Features

- Generate complete Jeopardy boards with 5 categories and 25 questions
- LLM-powered category and question generation
- Customizable difficulty progression
- Support for daily doubles
- Command-line interface for easy board generation

## Usage

### Python API

```python
import asyncio
from app.ai.board_generation.generator import BoardGenerator

async def generate_sample_board():
    generator = BoardGenerator()
    file_path = await generator.generate_and_save_board(
        board_name="my_custom_board",
        add_daily_doubles=True
    )
    print(f"Board saved to: {file_path}")

asyncio.run(generate_sample_board())
```

### Command Line

```bash
# Generate a single board
python -m app.ai.board_generation.cli --name my_board

# Generate multiple boards
python -m app.ai.board_generation.cli --count 3 --name batch

# Use a different model
python -m app.ai.board_generation.cli --model gpt-4

# Disable daily doubles
python -m app.ai.board_generation.cli --no-daily-doubles
```

## Board Format

The generated boards follow the standard format used by the application:

```json
{
  "contestants": [
    {"name": "Player 1", "score": 0},
    {"name": "Player 2", "score": 0},
    {"name": "Player 3", "score": 0}
  ],
  "categories": [
    {
      "name": "Category Name",
      "questions": [
        {
          "clue": "Clue text",
          "answer": "Correct response",
          "value": 200,
          "daily_double": false,
          "type": "text"
        },
        // More questions...
      ]
    },
    // More categories...
  ],
  "final": {
    "category": "Final Jeopardy",
    "clue": "Final clue",
    "answer": "Final answer"
  }
}
``` 