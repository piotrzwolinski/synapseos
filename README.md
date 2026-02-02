# Graph Chatbot

A full-stack chatbot application with Python/FastAPI backend and React/Next.js frontend.

## Tech Stack

- **Backend**: Python, FastAPI, Google Gemini AI, Neo4j
- **Frontend**: Next.js, React, shadcn/ui, Tailwind CSS

## Setup

### Backend

```bash
cd backend
source venv/bin/activate
uvicorn main:app --reload
```

Backend runs on http://localhost:8000

### Frontend

```bash
cd frontend
npm run dev
```

Frontend runs on http://localhost:3000

## API Endpoints

- `POST /chat` - Send a message to the chatbot
- `POST /chat/clear` - Clear chat history
- `GET /graph/stats` - Get Neo4j graph statistics
