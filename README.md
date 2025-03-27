This app lets you play online Jeopardy with an AI host and custom, dynamically-generated game boards.

LLM-powered stuff (board generation, response evaluation, etc.) and synthesized voices are provided by [Inworld AI](https://inworld.ai/), so you'll need a `.env` file with your `INWORLD_API_KEY`.

# Development Setup

1. In root, create/activate your virtual environment
2. In `app` folder, run `pip install -r requirements.txt`
3. In the `frontend` folder, run `npm run build`
2. In the root, run `uvicorn app.main:app --reload`

Access the app at `http://localhost:8000/`

# Serving to Online Players

You can play this online with friends using [ngrok](https://ngrok.com/).

1. In frontend, run `npm run build`
2. Start the server with `uvicorn app.main:app`
3. Start ngrok with `ngrok http 8000`

Direct your friends to the ngrok URL and enjoy a game of Jeopardy!

# Build Notes

This app was built as an experiment with 'vibe coding', so apologies for any code which is myopic, conflicting, or insecure.