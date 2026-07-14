import sys
import csv
import json
import time
import asyncio
from pathlib import Path
from uuid import uuid4


# --------------------------------------------------
#  IMPORT BACKEND HOST
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "src" / "backend"

sys.path.insert(0, str(BACKEND_DIR))

from host import OllamaMCPHost, MCP_SERVER_SCRIPTS


# --------------------------------------------------
#  FILE PATHS
# --------------------------------------------------

CSV_INPUT_PATH = Path(__file__).parent / "flight_queries_100_unique_each_duplicated.csv"
RESULTS_PATH = Path(__file__).parent / "duplicated_results_no_cache.csv"


# --------------------------------------------------
#  CSV LOADING
# --------------------------------------------------

def load_queries_from_csv(csv_path: Path):
    queries = []


    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        if "query" not in reader.fieldnames:
            raise ValueError(
                f"CSV must contain a column named 'query'. "
                f"Found columns: {reader.fieldnames}"
            )

        for row in reader:
            query = row["query"].strip()

            if query:
                queries.append(query)

    return queries


# --------------------------------------------------
#  BENCHMARK LOGIC
# --------------------------------------------------

async def run_benchmark():
    queries = load_queries_from_csv(CSV_INPUT_PATH)

    print(f"Loaded {len(queries)} queries from: {CSV_INPUT_PATH}")

    host = OllamaMCPHost(MCP_SERVER_SCRIPTS)

    print("Starting MCP host...")
    await host.startup()

    results = []

    user_info = {
        "user_id": "user_001",
        "name": "Benchmark User",
        "email": "benchmark@example.com",
    }

    try:
        for index, query in enumerate(queries, start=1):
            session_id = str(uuid4())

            print(f"\n[{index}/{len(queries)}] Query: {query}")

            # ------------------------------------------
            #  1. Measure Ollama/tool-decision latency
            # ------------------------------------------

            ollama_start = time.perf_counter()

            decision_result = await host.process_query_with_auth(
                query=query,
                session_id=session_id,
                conversation_history=[],
                user_info=user_info,
            )

            ollama_end = time.perf_counter()
            ollama_latency = ollama_end - ollama_start

            needs_tool = decision_result.get("needs_authorization", False)

            tool_name = None
            tool_args = None
            tool_latency = 0.0
            final_reply = decision_result.get("reply", "")

            # ------------------------------------------
            #  2. Bypass authorization and execute tool
            # ------------------------------------------

            if needs_tool:
                tool_data = decision_result["tool_data"]

                tool_name = tool_data["tool_name"]
                tool_args = tool_data["tool_args"]

                tool_latency = 0
                tool_llama_latency = 0

                final_reply, tool_latency, tool_llama_latency = await host.execute_tool_call(
                    tool_name=tool_name,
                    tool_args=tool_args,
                    query=query,
                    conversation_history=[],
                    user_info=user_info,
                    benchmark_mode = True
                )
            total_latency = ollama_latency + tool_latency + tool_llama_latency

            row = {
                "query_id": index,
                "query": query,
                "needs_tool": needs_tool,
                "tool_name": tool_name or "",
                "tool_args": json.dumps(tool_args, ensure_ascii=False) if tool_args else "",
                "tool_decision_latency_seconds": round(ollama_latency, 4),
                "tool_pipeline_latency_seconds": round(tool_latency, 4),
                "final_answer_formation_latency_seconds": round(tool_llama_latency, 4) if needs_tool else "",
                "total_latency_seconds": round(total_latency, 4),
                "reply_preview": final_reply[:300].replace("\n", " "),
            }

            results.append(row)

            print(f"Ollama latency: {ollama_latency:.4f}s")
            print(f"Tool latency:   {tool_latency:.4f}s")
            print(f"Final answer formation latency: {tool_llama_latency:.4f}s" if needs_tool else "")
            print(f"Total latency:  {total_latency:.4f}s")
            print(f"Tool used:      {tool_name}")

    finally:
        print("\nShutting down MCP host...")
        await host.shutdown()

    # ------------------------------------------
    #  Save results to CSV
    # ------------------------------------------

    fieldnames = [
        "query_id",
        "query",
        "needs_tool",
        "tool_name",
        "tool_args",
        "tool_decision_latency_seconds",
        "tool_pipeline_latency_seconds",
        "final_answer_formation_latency_seconds",
        "total_latency_seconds",
        "reply_preview",
    ]

    with open(RESULTS_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print("\nBenchmark complete.")
    print(f"Saved results to: {RESULTS_PATH}")


if __name__ == "__main__":
    asyncio.run(run_benchmark())