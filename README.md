# Finance Agent — Frontend

A React-based chat interface for interacting with the Finance Agent, a multi-trial AI system that answers financial questions using tool-augmented reasoning with self-evaluation and reflection loops.

## Features

- **Streaming Chat** — Real-time Server-Sent Events (SSE) streaming that surfaces each step of the agent's reasoning: tool calls, intermediate results, self-evaluation, reflection, and final answers.
- **Multi-Agent Support** — Connects to multiple specialized agents (Equity Research Analyst, Market Intelligence Associate, Portfolio Risk Analyst, Financial Advisor Assistant) and routes queries automatically.
- **Chat History** — Sidebar with full conversation history, rename, and delete support.
- **Evaluation Dashboard** — View benchmark results for each agent including task/step success rates, latency percentiles, hallucination rates, and per-category breakdowns.
- **Skills Management** — Browse, create, edit, and delete agent skills. Inspect skill definitions and associated files with an inline file viewer.
- **File Uploads** — Attach data files to conversations; uploaded files are tracked per chat.
- **Configurable Parameters** — Adjust the model, max trials, and confidence threshold directly from the input box.

## Tech Stack

| Layer | Technology |
|-------|------------|
| Framework | React 19 |
| Build Tool | Vite 6 |
| Styling | Tailwind CSS 4 |
| Icons | Lucide React |
| Markdown | react-markdown |
| Linting | ESLint 9 |

## Project Structure

```
capstone_frontend/
├── frontend/               # React application
│   ├── public/
│   ├── src/
│   │   ├── main.jsx        # Entry point
│   │   ├── App.jsx          # Root component, routing & state
│   │   ├── index.css        # Global styles & Tailwind config
│   │   ├── services/
│   │   │   └── api.js       # API client (SSE streaming, REST)
│   │   └── components/
│   │       ├── Sidebar.jsx        # Navigation & chat history
│   │       ├── WelcomeHeader.jsx  # Landing screen header
│   │       ├── InputBox.jsx       # Chat input with config controls
│   │       ├── ChatMessage.jsx    # Message rendering (all event types)
│   │       ├── DataContext.jsx     # Uploaded data panel
│   │       ├── EvaluationView.jsx # Agent evaluation dashboard
│   │       └── SkillsView.jsx     # Skill browser & editor
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── backend/                # FastAPI backend server
│   ├── server.py
│   ├── requirements.txt
│   └── .venv/
└── start.sh                # One-command launcher for both services
```

## Prerequisites

- **Node.js** >= 18
- **Python** >= 3.10 (for the backend)

## Getting Started

### Quick Start (recommended)

The included `start.sh` script installs all dependencies and launches both the frontend dev server and the mock backend in one step:

```bash
./start.sh
```

This will:

1. Install frontend npm dependencies (if `node_modules` is missing)
2. Create a Python virtual environment and install backend dependencies
3. Start the mock backend on **http://localhost:8000**
4. Start the Vite dev server on **http://localhost:5173**

Press `Ctrl+C` to stop both services.

### Manual Setup

If you prefer to run the services separately:

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

The dev server starts at **http://localhost:5173** and proxies `/api` requests to `http://localhost:8000`.

**Backend:**

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn server:app --reload --port 8000
```

## Available Scripts

Run these from the `frontend/` directory:

| Command | Description |
|---------|-------------|
| `npm run dev` | Start the Vite development server |
| `npm run build` | Build for production |
| `npm run preview` | Preview the production build locally |
| `npm run lint` | Run ESLint |

## API Overview

The frontend communicates with the backend through these endpoints:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/chat` | Send a question; returns an SSE stream of agent events |
| `GET` | `/api/chats` | List all chat sessions |
| `GET` | `/api/chats/:id` | Retrieve a full chat with messages |
| `PATCH` | `/api/chats/:id` | Rename a chat |
| `DELETE` | `/api/chats/:id` | Delete a chat |
| `GET` | `/api/agents` | List available agents |
| `GET` | `/api/evaluations` | Get agent benchmark results |
| `GET` | `/api/skills` | List all skills |
| `POST` | `/api/skills` | Create a new skill |
| `PATCH` | `/api/skills/:id` | Update a skill |
| `DELETE` | `/api/skills/:id` | Delete a user-created skill |

## Connecting to the Real Backend

By default, Vite proxies all `/api` requests to `http://localhost:8000`. To point at a different backend, update the proxy target in `frontend/vite.config.js`:

```js
server: {
  proxy: {
    '/api': {
      target: 'http://your-backend-host:port',
      changeOrigin: true,
    },
  },
},
```
