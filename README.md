# BNY Agent

A React-based chat interface for a multi-trial self-evolving AI system that answers questions and complete tasks using tool-augmented reasoning with self-evaluation and reflection loops.

## Features

- **Streaming Chat** — Real-time Server-Sent Events (SSE) streaming that surfaces each step of the agent's reasoning: tool calls, intermediate results, self-evaluation, reflection, and final answers.
- **Live Browser View** — Optional real-time browser rendering over WebSocket so you can watch the agent's Chromium session as it navigates and interacts with pages.
- **Multi-Agent Support** — Connects to multiple specialized agents (Equity Research Analyst, Market Intelligence Associate, Portfolio Risk Analyst, Financial Advisor Assistant) and routes queries automatically.
- **Chat History** — Sidebar with full conversation history, rename, and delete support.
- **Evaluation Dashboard** — View benchmark results for each agent including task/step success rates, latency percentiles, hallucination rates, and per-category breakdowns.
- **Skills Management** — Browse, create, edit, and delete agent skills. Inspect skill definitions and associated files with an inline file viewer.
- **File Uploads** — Attach data files to conversations; uploaded files are tracked per chat.
- **Configurable Parameters** — Adjust the model, max trials, and confidence threshold directly from the input box.

## Tech Stack

| Layer      | Technology     |
| ---------- | -------------- |
| Framework  | React 19       |
| Build Tool | Vite 6         |
| Styling    | Tailwind CSS 4 |
| Icons      | Lucide React   |
| Markdown   | react-markdown |
| Linting    | ESLint 9       |

## Project Structure

```text
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
│   │       ├── DataContext.jsx    # Uploaded data panel
│   │       ├── EvaluationView.jsx # Agent evaluation dashboard
│   │       └── SkillsView.jsx     # Skill browser & editor
│   ├── package.json
│   └── vite.config.js
├── backend/                # FastAPI backend server
│   ├── server.py # Main API entrypoint (FastAPI)
│   ├── .env # Environment variables & api keys
│   ├── requirements.txt # Backend dependencies
│   │
│   ├── skills/ # 📁 Persisted skill storage
│   │   └── [skill-name]/SKILL.md # Individual skill definitions
│   │   └── ...
│   │
│   ├── reflexion_agent/ # 📁 Agent Interaction Loop
│   │   ├── agent.py # Core agent loop and OpenHands integration
│   │   ├── evaluator.py # Assesses agent output correctness
│   │   ├── reflector.py # Generates self-reflection feedback on failure
│   │   └── memory.py # Manages conversation history/trajectory
│   │
│   ├── skills_ingestor/ # 📁 Skill Creation Tools
│   │   ├── mm_train.py # Multimodal trainer (video/audio -> skills)
│   │   └── prompts.py # System prompts for skill extraction
│   │
│   └── skillsbench/ # 📁 Automated Evaluation Framework
│       ├── experiments/
│       │   ├── skill_evaluation_framework.py # Orchestrator for evaluating skills against tasks
│       │   └── skill-eval-runs/ # Evaluation results (JSON/CSV)
│       └── tasks/ # 📁 Tasks/environments for evaluation
└── start.sh                # One-command launcher for all services
```

## Prerequisites

- **Node.js** >= 18
- **Python** >= 3.10 (for the backend)

## Getting Started

### 1. Configuration

The real agent requires an LLM API key.

Copy the example environment variables:

```bash
cd backend
cp .env.example .env
```

Then edit `backend/.env` and add your **OpenRouter / OpenAI** API Keys:

```env
OPENROUTER_API_KEY=sk-or-v1-...
```

_(If `.env` is missing or invalid, the backend will gracefully fall back to a "Mock Mode" that simulates an agent)._

### 2. Quick Start (recommended)

The included `start.sh` script installs all dependencies and launches everything in one step:

```bash
./start.sh
```

This will automatically:

1. Install frontend npm dependencies
2. Create `backend/.venv` and install all Python requirements (including OpenHands)
3. Setup the `skillsbench` evaluation framework
4. Start the backend API on **http://localhost:8000**
5. Start the React frontend on **http://localhost:5173**

Press `Ctrl+C` in the terminal to cleanly stop all services.

### Skillsbench Setup (for skill evaluation)

If the "Run Evaluation" button fails or skill evaluation doesn't work, initialize the skillsbench environment manually:

```bash
cd backend/skillsbench
uv sync
```

This installs Harbor and other evaluation dependencies into `backend/skillsbench/.venv`.

### Manual Setup

If you prefer to run the services separately:

**Backend:**

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn server:app --reload --port 8000
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

The frontend dev server starts at **http://localhost:5173** and proxies `/api` requests to the backend.

### Live Browser Flags

The realtime browser panel is enabled by default. You can tune it with these environment variables:

```env
ENABLE_BROWSER_LIVE=true
BROWSER_LIVE_QUALITY=60
BROWSER_LIVE_MAX_W=1280
BROWSER_LIVE_MAX_H=800
VITE_LIVE_BROWSER=true
```

- `ENABLE_BROWSER_LIVE` toggles the backend WebSocket stream at `/ws/browser/:sessionId`.
- `BROWSER_LIVE_QUALITY` controls JPEG quality from `1` to `100`.
- `BROWSER_LIVE_MAX_W` / `BROWSER_LIVE_MAX_H` cap the streamed frame size.
- `VITE_LIVE_BROWSER` controls whether the employee page renders the browser panel.

## Available Scripts

Run these from the `frontend/` directory:

| Command           | Description                          |
| ----------------- | ------------------------------------ |
| `npm run dev`     | Start the Vite development server    |
| `npm run build`   | Build for production                 |
| `npm run preview` | Preview the production build locally |
| `npm run lint`    | Run ESLint                           |

## API Overview

The frontend communicates with the backend through these endpoints:

| Method   | Endpoint           | Description                                            |
| -------- | ------------------ | ------------------------------------------------------ |
| `POST`   | `/api/chat`        | Send a question; returns an SSE stream of agent events |
| `WS`     | `/ws/browser/:id`  | Stream live browser frames and navigation metadata     |
| `GET`    | `/api/chats`       | List all chat sessions                                 |
| `GET`    | `/api/chats/:id`   | Retrieve a full chat with messages                     |
| `PATCH`  | `/api/chats/:id`   | Rename a chat                                          |
| `DELETE` | `/api/chats/:id`   | Delete a chat                                          |
| `GET`    | `/api/agents`      | List available agents                                  |
| `GET`    | `/api/evaluations` | Get agent benchmark results                            |
| `GET`    | `/api/skills`      | List all skills                                        |
| `POST`   | `/api/skills`      | Create a new skill                                     |
| `PATCH`  | `/api/skills/:id`  | Update a skill                                         |
| `DELETE` | `/api/skills/:id`  | Delete a user-created skill                            |

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
