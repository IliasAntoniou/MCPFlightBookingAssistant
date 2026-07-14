# MCPFlightBookingAssistant

An AI-powered flight booking application demonstrating the Model Context Protocol (MCP). Users interact with a conversational AI assistant through a web interface to search flights and manage bookings. The system runs a **local Ollama/Llama** model as the reasoning host and connects it to MCP servers for natural language access to flight data and booking operations — no external LLM API or per-request cost. It also includes an optional exact + semantic-similarity caching layer and a benchmark suite for evaluating cache effectiveness.

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│ Web Frontend (index.html)                           │
│ - Chat interface & user authentication              │
│ - Tool authorization (approve/deny actions)         │
└────────────────────┬────────────────────────────────┘
                     ▲
                     │ HTTP
                     ▼
┌─────────────────────────────────────────────────────┐
│ Backend Host (host.py) - Port 8001                  │
│ - Ollama/Llama client + MCP client host             │
│ - Conversation & session management                 │
│ - Optional exact + semantic-similarity cache        │
└──────┬───────────────────────────────┬──────────────┘
       │ HTTP                          │ STDIO
       ▼                               ▼
┌──────────────────┐        ┌──────────┴───────────────┐
│ Ollama Server    │        ▲                          ▲
│ Port 11434       │        │                          │
│ (local LLM)      │  ┌─────▼──────────┐   ┌───────────▼──────┐
└──────────────────┘  │ flightsearch.py│   │ flightbooking.py │
                      │ MCP Server     │   │ MCP Server       │
                      └─────┬──────────┘   └───────────┬──────┘
                            │ HTTP                     │ HTTP
                            └─────────────┬────────────┘
                                          ▼
┌─────────────────────────────────────────────────────┐
│ Flight API (flight_api.py) - Port 8000              │
│ - SQLite database (100k flights, seat tracking)     │
│ - REST endpoints for search & booking               │
└─────────────────────────────────────────────────────┘
```

## ✨ Key Features

- **Runs Fully Locally**: A local Ollama/Llama model powers the assistant — no external API keys or usage costs
- **Natural Language Interface**: Chat with AI to search and book flights
- **MCP Integration**: Two MCP servers (search & booking) using JSON-RPC over STDIO
- **Tool Authorization**: Users approve AI actions before execution
- **Seat Management**: Real-time tracking with 100 seats per flight, prevents overbooking
- **User Authentication**: Profile management with persistent sessions
- **100,000 Flights**: SQLite database auto-generated and seeded on first startup
- **Caching Layer**: Optional exact-match and semantic-similarity caches for LLM/tool responses (toggleable in `host.py`)
- **Benchmark Suite**: Scripts and datasets to measure cache hit rates and latency (`benchmark/`)
- **Context Awareness**: AI understands conversation history and current date/time

## 📁 Project Structure

```
MCPFlightBookingAssistant/
├── src/
│   ├── backend/
│   │   ├── host.py             # Main FastAPI app + Ollama/Llama + MCP client host
│   │   ├── config.py           # Centralized configuration (airports, airlines, flight generation)
│   │   ├── db.py               # SQLite operations (auto-creates & seeds the database)
│   │   ├── flight_api.py       # FastAPI flight search/booking API
│   │   ├── exact_cache.py      # Exact-match response cache (LRU)
│   │   ├── similarity_cache.py # Semantic-similarity response cache (embeddings)
│   │   ├── test_ollama.py      # Standalone Ollama connectivity/model test
│   │   ├── flight_app.db       # SQLite database — GENERATED on first run (git-ignored)
│   │   └── .env                # Optional local config (git-ignored)
│   │
│   ├── frontend/
│   │   └── index.html          # Web UI with chat interface
│   │
│   └── MCPservers/
│       ├── flightsearch.py     # MCP server for flight search
│       └── flightbooking.py    # MCP server for booking management
│
├── benchmark/                  # Cache benchmark scripts, query datasets & analysis
│   ├── benchmark.py
│   ├── BENCHMARK_ANALYSIS.md
│   └── *.csv                   # Query sets and captured results
├── requirements.txt            # Python dependencies
├── start.ps1                   # PowerShell startup script
├── start.bat                   # Batch startup script
└── README.md
```

> **Note:** `flight_app.db` is not committed to the repository. It is created and seeded with 100,000 flights automatically on first startup (see `db.py`).

## 🛠️ Technology Stack

- **Backend**: Python 3.13, FastAPI, Uvicorn
- **AI Model**: Ollama running a local Llama model (default `llama3.2`)
- **Embeddings**: `sentence-transformers` (`all-mpnet-base-v2`) for the semantic-similarity cache
- **MCP Framework**: FastMCP, MCP Python SDK
- **Database**: SQLite
- **Frontend**: Vanilla HTML/CSS/JavaScript
- **Transport**: STDIO (Standard Input/Output) for MCP communication

## 📦 Installation

### Prerequisites
- Python 3.13+
- [Ollama](https://ollama.com/) installed and running locally
- UV package manager (for running MCP servers)

### Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/IliasAntoniou/MCPFlightBookingAssistant.git
   cd MCPFlightBookingAssistant
   ```

2. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Pull the Llama model with Ollama**
   ```bash
   ollama pull llama3.2
   ```

4. **(Optional) Configure environment variables**

   The application works out of the box against a local Ollama instance. To override defaults, create `src/backend/.env`:
   ```
   OLLAMA_URL=http://localhost:11434
   OLLAMA_MODEL=llama3.2
   ```

5. **Initialize database** (automatic on first run)

   The system automatically generates 100,000 flights on first startup.

## 🚀 Running the Application

### Option 1: Automated Start (Recommended)

**Windows PowerShell:**
```powershell
.\start.ps1
```

**Windows Command Prompt:**
```cmd
start.bat
```

This will:
1. Start the Ollama server (port 11434)
2. Start the Flight API server (port 8000)
3. Start the Llama + MCP host (port 8001)
4. Open the web interface in your browser

### Option 2: Manual Start

**Terminal 1 - Ollama:**
```bash
ollama serve
```

**Terminal 2 - Flight API:**
```bash
cd src/backend
python -m uvicorn flight_api:app --reload --port 8000
```

**Terminal 3 - Main Host:**
```bash
cd src/backend
python -m uvicorn host:app --reload --port 8001
```

**Terminal 4 - Open Browser:**
```bash
start src/frontend/index.html
```

## 💬 Usage

1. **Login** with demo credentials:
   - Email: `john.doe@example.com`
   - Password: `secret123`

2. **Chat with the AI assistant**:
   - "Search flights from ATH to BCN on 2026-05-15"
   - "Show me my bookings"
   - "Book flight FL-012345 for John Doe"

   > Generated flights span 30 days starting **2026-05-09** (see `config.py`), so use dates in that window when searching.

3. **Approve tool calls** when prompted

4. **Manage your profile** via the profile page

## 🔧 MCP Tools

**Flight Search** (`flightsearch.py`)
- `search_flights` - Find flights by origin, destination, and date
- `getflightbyid` - Get details for a specific flight
- Features: input validation, structured logging

**Flight Booking** (`flightbooking.py`)
- `book_flight` - Create confirmed booking (checks seat availability)
- `hold_flight` - Temporary hold with expiration
- `confirm_held_booking` - Convert hold to confirmed booking
- `cancel_booking` - Delete booking and restore seats
- `get_booking_details` - View booking information
- `get_user_bookings` - List all user bookings
- Features: Atomic seat updates, overbooking prevention, hold expiration tracking

## ⚡ Caching & Benchmarks

The host supports two optional caching strategies for LLM/tool responses, controlled by flags near the top of `host.py`:

- `USE_EXACT_CACHE` — exact-match cache (`exact_cache.py`), LRU eviction
- `USE_SIMILARITY_CACHE` — semantic-similarity cache (`similarity_cache.py`) using `sentence-transformers` embeddings with a cosine-similarity threshold

Both are disabled by default. The `benchmark/` directory contains query datasets, a benchmark runner (`benchmark.py`), captured results, and a written analysis (`BENCHMARK_ANALYSIS.md`) comparing a no-cache baseline against the combined exact + similarity cache.

## 🔒 How It Works

1. User sends message via web interface
2. The local Llama model determines if tool execution is needed
3. User approves/denies the tool call
4. MCP server executes the tool and returns the result
5. AI formats the response and displays it to the user

All tool executions require explicit user approval for safety.

## 📝 Notes

This is a thesis project demonstrating Model Context Protocol integration with a locally hosted conversational LLM for flight booking operations, including an investigation into semantic caching of LLM-agent responses.

## 🔗 Resources

- [Model Context Protocol Documentation](https://modelcontextprotocol.io/)
- [FastMCP Framework](https://github.com/jlowin/fastmcp)
- [Ollama](https://ollama.com/)
- [Sentence-Transformers](https://www.sbert.net/)
