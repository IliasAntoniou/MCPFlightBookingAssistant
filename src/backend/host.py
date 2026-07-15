import os
import re
import sys
import json
import asyncio
from pathlib import Path
from contextlib import AsyncExitStack
from typing import Optional, Dict, Any, List
from typing import Union, Tuple

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from uuid import uuid4
from similarity_cache import Similarity_Cache
from sentence_transformers import SentenceTransformer
from exact_cache import Exact_Cache

from dotenv import load_dotenv

import requests
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Status messages below contain emoji; on Windows stdout defaults to cp1252,
# which raises UnicodeEncodeError on them. Force UTF-8 output.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# --------------------------------------------------
#  ENV + LLAMA CLIENT
# --------------------------------------------------
# Load .env from the same directory as this script
ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

# Local Ollama configuration
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")

USE_SIMILARITY_CACHE = False
USE_EXACT_CACHE = False

#similarity cache initialization
similaritycache = Similarity_Cache(cache_size=1000, threshold=0.99, embedding_model=SentenceTransformer("all-mpnet-base-v2"), eviction_policy="LRU")

#exact cache initialization
exactcache = Exact_Cache(cache_size=1000, eviction_policy="LRU")

tool_call_request_key = None
cached_tool_result = None

# Validate that Ollama is reachable
try:
    requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
except Exception as e:
    print(f"⚠️  Warning: Could not connect to Ollama at {OLLAMA_URL}: {e}")


# --------------------------------------------------
#  OLLAMA/LLAMA + MCP HOST
# --------------------------------------------------

class OllamaMCPHost:
    """
    Host component that:
      - connects to multiple MCP servers (flightsearch, flightbooking) via stdio
      - talks to a local Ollama/Llama model
      - optionally calls tools via MCP when the model asks
    """

    def __init__(self, server_script_paths: list[str]):
        self.server_script_paths = server_script_paths
        self.exit_stack = AsyncExitStack()
        self.sessions: Dict[str, ClientSession] = {}

    async def startup(self):
        """
        Start multiple MCP servers (via stdio_client) and initialize ClientSessions.
        """
        for script_path in self.server_script_paths:
            path = Path(script_path).resolve()
            if not path.exists():
                raise RuntimeError(f"MCP server script not found: {path}")
            if not path.is_file():
                raise RuntimeError(f"MCP server script path is not a file: {path}")

            # Using `uv run <script>`
            server_params = StdioServerParameters(
                command="uv",
                args=["--directory", str(path.parent), "run", path.name],
                env=None,
            )

            stdio_transport = await self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            read, write = stdio_transport

            session = await self.exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            await session.initialize()

            # Store session by server name (extracted from filename)
            server_name = path.stem
            self.sessions[server_name] = session

            tools_response = await session.list_tools()
            tool_names = [t.name for t in tools_response.tools]
            print(f"✅ Connected to MCP server '{server_name}'. Tools:", tool_names)

    async def shutdown(self):
        await self.exit_stack.aclose()

    async def process_query_with_auth(self, query: str, session_id: str, conversation_history: List[Dict[str, str]] = None, user_info: Dict[str, str] = None) -> Dict[str, Any]: # type: ignore
        """
        Process query and return authorization request if tool call is needed.
        """
        if not self.sessions:
            return {"reply": "MCP sessions not initialized on server.", "needs_authorization": False}
        
        if conversation_history is None:
            conversation_history = []
        
        if user_info is None:
            user_info = {}

        # Get tools from all MCP servers
        all_tools = []
        for server_name, session in self.sessions.items():
            tools_response = await session.list_tools()
            all_tools.extend(tools_response.tools)
        
        tools = all_tools

        # Build tool description
        tool_lines = []
        for t in tools:
            try:
                schema_json = json.dumps(t.inputSchema)
            except TypeError:
                schema_json = str(t.inputSchema)
            tool_lines.append(
                f"- {t.name}: {t.description or ''} | schema: {schema_json}"
            )
        tools_block = "\n".join(tool_lines) if tool_lines else "(no tools)"

        system_prompt = f"""
You are a flight booking assistant that can call tools to help users.
THE MOST IMPORTANT PART IS READ THE USER QUESTION AND ONLY IF HE ASKS ABOUT AN ACTION CHECK IF YOU SHOULD USE A TOOL
THE TOOL DESCRIPTIONS ARE BELOW, READ THEM CAREFULLY AND USE THEM WHEN NECESSARY WITH THE CORRECT ARGUMENTS.
LOOK CAREFULLY AT THE TOOL CALLING RULES AND FOLLOW THEM EXACTLY. DISTRINGUISH BOOK FROM SEARCH.
AVAILABLE TOOLS:
{tools_block}

TOOL CALLING RULES:
1. When you need to use a tool, respond with ONLY a JSON object (no other text):
{{
  "tool": "tool_name_here",
  "args": {{
    "param1": "value1",
    "param2": "value2"
  }}
}}

2. If you can answer without a tool, respond normally with helpful text.

3. destinations should be in IATA code format (e.g. ATH, BCN).

4. Dates should be in YYYY-MM-DD format.s
EXAMPLES:
User: "search flights from ATH to BCN on 2025-12-03"
Response: {{"tool": "search_flights", "args": {{"origin": "ATH", "destination": "BCN", "date": "2025-12-03"}}}}

User: "show me my bookings"
Response: {{"tool": "get_user_bookings", "args": {{"user_id": "user_001"}}}}

User: "what is your name?"
Response: I'm your flight booking assistant! I can help you search for flights, manage bookings, and plan your travel.

RESPONSE FORMATTING (for non-tool answers):
- Use **bold** for important info
- Use bullet points for lists
- Use `code` for IDs
- Be clear and concise
        """.strip()

        # Get current date and time
        from datetime import datetime
        now = datetime.now()
        current_date = now.strftime("%A, %B %d, %Y")
        current_time = now.strftime("%I:%M %p")
        
        # Build user info context
        user_context = f"\n\nCurrent date and time: {current_date} at {current_time}"
        
        if user_info and "user_id" in user_info:
            user_context += f"\n\nLogged-in user information:\n- User ID: {user_info.get('user_id', 'N/A')}\n- Name: {user_info.get('name', 'N/A')}\n- Email: {user_info.get('email', 'N/A')}\n\nIMPORTANT: When the user asks about \"my bookings\" or \"my flights\", automatically use the User ID '{user_info.get('user_id')}' to call get_user_bookings. When booking flights, use the name '{user_info.get('name')}' and email '{user_info.get('email')}' automatically unless the user specifies different passenger details."
            print(f"👤 User info available: {user_info}")

        # Build conversation context
        context_text = ""
        if conversation_history:
            recent_history = conversation_history[-6:]  # Last 3 exchanges (6 messages)
            context_lines = []
            for msg in recent_history:
                role = "User" if msg["role"] == "user" else "Assistant"
                context_lines.append(f"{role}: {msg['message']}")
            context_text = "\n\nRecent conversation:\n" + "\n".join(context_lines)
            print(f"📝 Conversation context ({len(recent_history)} messages):\n{context_text}")

        # Ask Ollama whether to call a tool with conversation history
        """
        initial_text = self._call_ollama(
            f"{system_prompt}{user_context}{context_text}\n\nUser question:\n{query}"
        )
        """
        
        ollama_start_time = time.perf_counter()
        cached_response = None

        if USE_SIMILARITY_CACHE:
            cached_response = similaritycache.get(query)
        if cached_response is not None and USE_SIMILARITY_CACHE:
            print("Similarity Cache hit")
            initial_text = cached_response
            ollama_end_time = time.perf_counter()
            ollama_duration = ollama_end_time - ollama_start_time
            print(f"⏱️ Ollama response time (from cache): {ollama_duration:.2f} seconds")
        else:
            initial_text = self._call_ollama(
            f"{system_prompt}{user_context}\n\nUser question:\n{query}"
            )
            if USE_SIMILARITY_CACHE:
                similaritycache.put(query, initial_text)
        
        ollama_end_time = time.perf_counter()

        ollama_duration = ollama_end_time - ollama_start_time

        print(f"⏱️ Ollama response time: {ollama_duration:.2f} seconds")
        
        print(f"🤖 Model response: {initial_text[:200]}...")
        
        # Try to parse as JSON specifying a tool call
        parsed = self._extract_json(initial_text)
        
        if parsed:
            print(f"✅ Parsed JSON: {parsed}")
        else:
            print(f"❌ Could not extract JSON from response")

        if not parsed or "tool" not in parsed:
            # Not a tool call, return normal answer
            return {"reply": initial_text, "needs_authorization": False}

        tool_name = parsed["tool"]
        tool_args = parsed.get("args", {}) or {}

        # Request authorization from user
        auth_response = {
            "reply": f"The AI wants to call the tool: **{tool_name}**\n\nArguments: {json.dumps(tool_args, indent=2)}\n\nDo you authorize this action?",
            "needs_authorization": True,
            "tool_request": {
                "session_id": session_id,
                "tool_name": tool_name,
                "tool_args": tool_args
            },
            "tool_data": {
                "tool_name": tool_name,
                "tool_args": tool_args,
                "query": query,
                "conversation_history": conversation_history,
                "user_info": user_info
            }
        }
        
        return auth_response

    async def execute_tool_call(self, tool_name: str, tool_args: Dict[str, Any], query: str, conversation_history: List[Dict[str, str]] = None, user_info: Dict[str, str] = None, benchmark_mode: bool = False) -> Union[str, Tuple[str, float, float]]:
        """
        Execute the authorized tool call and return final answer.
        """
        if not self.sessions:
            return "MCP sessions not initialized on server."
        
        if conversation_history is None:
            conversation_history = []
        
        if user_info is None:
            user_info = {}

        tool_llama_duration = 0.0
        tool_start_time = time.perf_counter()
        # Find which session has this tool
        call_result = None

        tool_cache_key = json.dumps({"tool": tool_name,"args": tool_args},sort_keys=True)

        if USE_EXACT_CACHE:
            cached_tool_result = exactcache.get(tool_cache_key)

        if USE_EXACT_CACHE and cached_tool_result is not None:
            print("Exact cache hit for tool result")
            tool_end_time = time.perf_counter()
            tool_duration = tool_end_time - tool_start_time
            print(f"⏱️ Tool execution time (from cache): {tool_duration:.2f} seconds")

            if benchmark_mode:
                return cached_tool_result, tool_duration, tool_llama_duration
            return cached_tool_result
            
        for server_name, session in self.sessions.items():
            tools_response = await session.list_tools()
            tool_names = [t.name for t in tools_response.tools]
            if tool_name in tool_names:
                # Call MCP tool on the correct session
                try:
                    print(f"🔧 Executing authorized tool: {tool_name} (from {server_name}) with args {tool_args}")
                    call_result = await session.call_tool(tool_name, tool_args)
                    break
                except Exception as e:
                    error_text = f"Error calling tool '{tool_name}' with args {tool_args}: {e}"
                    return self._call_ollama(
                        f"User question: {query}\n\n"
                        f"There was an error calling the tool:\n{error_text}\n\n"
                        f"Explain the error to the user in normal natural language."
                    )
        
        if call_result is None:
            return f"Tool '{tool_name}' not found in any connected MCP server."

        call_result_str = str(call_result)

        tool_end_time = time.perf_counter()
        tool_duration = tool_end_time - tool_start_time
        print(f"⏱️ Tool execution time: {tool_duration:.2f} seconds")

        tool_llama_start = time.perf_counter()

        # Build user info context
        user_context = ""
        if user_info and "user_id" in user_info:
            user_context = f"\n\nLogged-in user information:\n- User ID: {user_info.get('user_id', 'N/A')}\n- Name: {user_info.get('name', 'N/A')}\n- Email: {user_info.get('email', 'N/A')}\n"

        # Get final answer from the local model

        final_answer = self._call_ollama(
            f"""You are now writing a final answer for the user.
Do NOT call any tools anymore and do NOT respond with JSON.
Just answer in normal, helpful natural language.
{user_context}
User question:
{query}

Tool '{tool_name}' was called with arguments:
{json.dumps(tool_args, indent=2)}

Tool returned (raw MCP result):
{call_result_str}

Please answer the user, summarizing the tool result in a helpful way.

Formatting guidelines:
- Use **bold** for important information (flight IDs, airports, prices)
- Use bullet points for lists of flights or options
- Use `code` for IDs like flight numbers or booking IDs
- Keep the response clear, organized, and easy to read
- If showing multiple flights, format them in a clean list
"""
        )
        print("saved in exact cache")
        if USE_EXACT_CACHE:
            exactcache.put(tool_cache_key, final_answer)
        tool_llama_end = time.perf_counter()
        tool_llama_duration = tool_llama_end - tool_llama_start
        if benchmark_mode:
            return final_answer, tool_duration, tool_llama_duration
        return final_answer

    @staticmethod
    def _call_ollama(prompt: str) -> str:
        """
        Helper: single-turn Ollama/Llama call with text in/out.
        """
        try:
            response = requests.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                },
                timeout=300
            )
            response.raise_for_status()
            result = response.json()
            return (result.get("response", "")).strip()
        except Exception as e:
            print(f"❌ Error calling Ollama: {e}")
            return f"Error communicating with local Llama model: {e}"

    @staticmethod
    def _extract_json(text: str) -> Optional[dict]:
        """
        Try to extract a JSON object from the model's response,
        even if it's wrapped in ```json fences or extra text.
        """
        # Look for ```json ... ``` or ``` ... ``` fences
        fence_match = re.search(
            r"```(?:json)?\s*(\{.*?\})\s*```",
            text,
            re.DOTALL
        )
        if fence_match:
            candidate = fence_match.group(1)
        else:
            # Fallback: try entire text
            candidate = text.strip()

        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None

        return None


# --------------------------------------------------
#  FASTAPI APP + UI CHAT ENDPOINT
# --------------------------------------------------

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # dev; tighten later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dynamically resolve MCP server script paths
CURRENT_DIR = Path(__file__).resolve().parent
MCP_SERVERS_DIR = CURRENT_DIR.parent / "MCPservers"
MCP_SERVER_SCRIPTS = [
    str(MCP_SERVERS_DIR / "flightsearch.py"),
    str(MCP_SERVERS_DIR / "flightbooking.py"),
]

host = OllamaMCPHost(MCP_SERVER_SCRIPTS)

# Session storage for pending tool calls
pending_tool_calls: Dict[str, Dict[str, Any]] = {}

# Conversation history storage: user_session_id -> list of messages
conversation_history: Dict[str, List[Dict[str, str]]] = {}

# User information storage: user_session_id -> user info
user_info_storage: Dict[str, Dict[str, str]] = {}


class ChatRequest(BaseModel):
    message: str
    user_session_id: Optional[str] = None  # Browser session ID for conversation history
    user_info: Optional[Dict[str, str]] = None  # User information from login (dict with user_id, email, name)


class ChatResponse(BaseModel):
    reply: str
    tool_request: Optional[dict] = None
    needs_authorization: bool = False


class ToolAuthorizationRequest(BaseModel):
    session_id: str
    authorized: bool


@app.on_event("startup")
async def on_startup():
    await host.startup()


@app.on_event("shutdown")
async def on_shutdown():
    await host.shutdown()


@app.get("/")
async def root():
    return {"status": "ok", "message": "Ollama/Llama + MCP host is running"}

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    session_id = str(uuid4())
    print(f"📨 Received chat request: message='{req.message[:50]}...', user_info={req.user_info}")
    
    # Get or create conversation history for this user session
    user_session_id = req.user_session_id or str(uuid4())
    if user_session_id not in conversation_history:
        conversation_history[user_session_id] = []
    
    # Store user info if provided
    if req.user_info:
        user_info_storage[user_session_id] = req.user_info
        print(f"👤 Stored user info for session {user_session_id}: {req.user_info}")
    
    # Get stored user info
    user_info = user_info_storage.get(user_session_id, None)
    
    # Process query with conversation context (pass history BEFORE adding current message)
    result = await host.process_query_with_auth(
        req.message, 
        session_id,
        conversation_history[user_session_id],
        user_info # type: ignore
    )
    
    # NOW add user message to history (after processing)
    conversation_history[user_session_id].append({
        "role": "user",
        "message": req.message
    })
    
    if result.get("needs_authorization"):
        # Add user_session_id to tool_data so we can update history after authorization
        result["tool_data"]["user_session_id"] = user_session_id
        pending_tool_calls[session_id] = result["tool_data"]
        # Don't add to history yet, wait for authorization
        return ChatResponse(
            reply=result["reply"],
            needs_authorization=True,
            tool_request=result["tool_request"]
        )
    
    # Add assistant response to history
    conversation_history[user_session_id].append({
        "role": "assistant",
        "message": result["reply"]
    })
    
    return ChatResponse(reply=result["reply"])


class ExecuteToolRequest(BaseModel):
    tool_name: str
    tool_args: Dict[str, Any]
    user_session_id: Optional[str] = None
    user_info: Optional[Dict[str, str]] = None


@app.post("/execute_tool")
async def execute_tool(req: ExecuteToolRequest):
    """
    Execute a tool call that was approved by the user.
    """
    try:
        # Get conversation history and user info
        user_session_id = req.user_session_id or "default"
        history = conversation_history.get(user_session_id, [])
        user_info = req.user_info or user_info_storage.get(user_session_id, {})
        
        # Create a query context for the tool execution
        query = f"Execute {req.tool_name} with arguments {req.tool_args}"
        
        # Execute the tool
        reply = await host.execute_tool_call(
            req.tool_name,
            req.tool_args,
            query,
            history,
            user_info
        )
        
        # Add to conversation history
        if user_session_id in conversation_history:
            conversation_history[user_session_id].append({
                "role": "assistant",
                "message": reply
            })
        
        return {"reply": reply, "error": None}
    except Exception as e:
        print(f"❌ Error executing tool: {e}")
        return {"reply": None, "error": str(e)}


@app.post("/authorize_tool")
async def authorize_tool(req: ToolAuthorizationRequest):
    session_id = req.session_id
    
    if session_id not in pending_tool_calls:
        raise HTTPException(status_code=404, detail="Session not found")
    
    tool_data = pending_tool_calls.pop(session_id)
    
    if not req.authorized:
        denied_reply = "Tool call was denied by user."
        # Add denied response to history if user_session_id exists
        if "user_session_id" in tool_data:
            user_session_id = tool_data["user_session_id"]
            if user_session_id in conversation_history:
                conversation_history[user_session_id].append({
                    "role": "assistant",
                    "message": denied_reply
                })
        return ChatResponse(reply=denied_reply)
    
    # Execute the tool call
    reply = await host.execute_tool_call(
        tool_data["tool_name"],
        tool_data["tool_args"],
        tool_data["query"],
        tool_data.get("conversation_history", []),
        tool_data.get("user_info", {})
    )
    
    # Add assistant response to history
    if "user_session_id" in tool_data:
        user_session_id = tool_data["user_session_id"]
        if user_session_id in conversation_history:
            conversation_history[user_session_id].append({
                "role": "assistant",
                "message": reply
            })
    
    return ChatResponse(reply=reply)
