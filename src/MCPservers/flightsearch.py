import os
from datetime import datetime
from typing import Any, List, Dict, Optional
import time
import logging
from pathlib import Path

import httpx
from pydantic import BaseModel, Field, validator
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("flightsearch")

FLIGHT_API_BASE = os.environ.get("FLIGHT_API_BASE", "http://localhost:8000")

# -------------------------
# Logging setup
# -------------------------

DEFAULT_LOG_PATH = Path(__file__).parent / "flightsearch.log"
LOG_FILE = Path(os.environ.get("FLIGHTSEARCH_LOG_FILE", str(DEFAULT_LOG_PATH)))

logger = logging.getLogger("flightsearch")
logger.setLevel(logging.INFO)

if not logger.handlers:
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s"
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)

logger.info("==== Flightsearch MCP server starting ====")
logger.info(f"Logging to file: {LOG_FILE.resolve()}")


# -------------------------
# Validation Models
# -------------------------

class FlightSearchValidation(BaseModel):
    """Validation model for flight search parameters."""
    origin: str = Field(..., min_length=3, max_length=3, pattern=r'^[A-Z]{3}$')
    destination: str = Field(..., min_length=3, max_length=3, pattern=r'^[A-Z]{3}$')
    date: str = Field(..., pattern=r'^\d{4}-\d{2}-\d{2}$')

    @validator("date")
    def validate_date(cls, v):
        try:
            date_obj = datetime.strptime(v, "%Y-%m-%d").date()

            if date_obj < datetime.now().date():
                raise ValueError("Date cannot be in the past")

            return v

        except ValueError as e:
            if "does not match format" in str(e):
                raise ValueError("Date must be in YYYY-MM-DD format")
            raise

    @validator("origin", "destination")
    def validate_airport_code(cls, v):
        if not v.isupper():
            raise ValueError("Airport code must be uppercase")
        return v


class FlightIdValidation(BaseModel):
    """Validation model for flight ID."""
    flight_id: str = Field(..., pattern=r'^FL-\d{6}$')


def validate_search_params(
    origin: str,
    destination: str,
    date: str
) -> tuple[bool, Optional[str]]:
    """Validate flight search parameters. Returns (is_valid, error_message)."""
    try:
        origin = origin.upper()
        destination = destination.upper()

        FlightSearchValidation(
            origin=origin,
            destination=destination,
            date=date
        )

        return True, None

    except Exception as e:
        error_msg = str(e)

        if "origin" in error_msg.lower() or "destination" in error_msg.lower():
            if "3" in error_msg:
                return False, "Airport codes must be exactly 3 letters (e.g., ATH, LHR, BCN)."
            return False, "Airport codes must be 3 uppercase letters (e.g., ATH, LHR, BCN)."

        if "date" in error_msg.lower():
            if "past" in error_msg.lower():
                return False, "Cannot search for flights in the past. Please select a future date."
            return False, "Invalid date format. Please use YYYY-MM-DD format (e.g., 2025-12-15)."

        return False, f"Validation error: {error_msg}"


def validate_flight_id(flight_id: str) -> tuple[bool, Optional[str]]:
    """Validate flight ID format. Returns (is_valid, error_message)."""
    try:
        FlightIdValidation(flight_id=flight_id)
        return True, None

    except Exception:
        return False, "Invalid flight ID format. Flight ID should be in format FL-XXXXXX (e.g., FL-001234)."


# -------------------------
# API Helper Functions
# -------------------------

async def fetch_flight_by_id(flight_id: str) -> Dict[str, Any] | None:
    url = f"{FLIGHT_API_BASE}/flights/{flight_id}"
    start_time = time.perf_counter()

    logger.info(f"API request started: GET {url}")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()

            flight = response.json()
            duration = time.perf_counter() - start_time

            logger.info(
                f"API request successful: flight_id={flight_id} "
                f"status={response.status_code} duration={duration:.3f}s"
            )

            return flight

    except httpx.HTTPStatusError as e:
        duration = time.perf_counter() - start_time

        logger.error(
            f"API request failed: flight_id={flight_id} "
            f"status={e.response.status_code} duration={duration:.3f}s"
        )

        return None

    except httpx.TimeoutException:
        duration = time.perf_counter() - start_time

        logger.error(
            f"API request timed out: flight_id={flight_id} "
            f"duration={duration:.3f}s"
        )

        return None

    except Exception:
        duration = time.perf_counter() - start_time

        logger.exception(
            f"Unexpected API error: flight_id={flight_id} "
            f"duration={duration:.3f}s"
        )

        return None


async def fetch_flights_from_api(
    origin: str,
    destination: str,
    date: str,
) -> List[Dict[str, Any]] | None:
    url = f"{FLIGHT_API_BASE}/flights"
    start_time = time.perf_counter()

    logger.info(
        f"API request started: GET {url} "
        f"origin={origin} destination={destination} date={date}"
    )

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                params={
                    "origin": origin,
                    "destination": destination,
                    "date": date,
                },
                timeout=10.0,
            )

            response.raise_for_status()

            flights = response.json()
            flight_count = len(flights) if isinstance(flights, list) else 0
            duration = time.perf_counter() - start_time

            logger.info(
                f"API request successful: origin={origin} "
                f"destination={destination} date={date} "
                f"status={response.status_code} "
                f"flights_found={flight_count} "
                f"duration={duration:.3f}s"
            )

            return flights

    except httpx.HTTPStatusError as e:
        duration = time.perf_counter() - start_time

        logger.error(
            f"API request failed: origin={origin} "
            f"destination={destination} date={date} "
            f"status={e.response.status_code} "
            f"duration={duration:.3f}s"
        )

        return None

    except httpx.TimeoutException:
        duration = time.perf_counter() - start_time

        logger.error(
            f"API request timed out: origin={origin} "
            f"destination={destination} date={date} "
            f"duration={duration:.3f}s"
        )

        return None

    except Exception:
        duration = time.perf_counter() - start_time

        logger.exception(
            f"Unexpected API error: origin={origin} "
            f"destination={destination} date={date} "
            f"duration={duration:.3f}s"
        )

        return None


def format_flight(flight: Dict[str, Any]) -> str:
    return (
        f"[{flight.get('id', 'UNKNOWN')}] "
        f"{flight.get('origin', '???')} → {flight.get('destination', '???')} | "
        f"Date: {flight.get('date', '????-??-??')} | "
        f"Airline: {flight.get('airline', 'Unknown')} | "
        f"Price: {flight.get('price', 'N/A')} EUR"
    )


# -------------------------
# MCP Tools
# -------------------------

@mcp.tool()
async def getflightbyid(flight_id: str) -> str:
    """Get details of a specific flight by its ID."""
    tool_start = time.perf_counter()

    logger.info(f"Tool called: getflightbyid flight_id={flight_id}")

    is_valid, error_msg = validate_flight_id(flight_id)

    if not is_valid:
        duration = time.perf_counter() - tool_start

        logger.warning(
            f"Tool failed validation: getflightbyid "
            f"flight_id={flight_id} error={error_msg} "
            f"duration={duration:.3f}s"
        )

        return f"❌ {error_msg}"

    flight = await fetch_flight_by_id(flight_id)

    duration = time.perf_counter() - tool_start

    if flight is None:
        logger.error(
            f"Tool failed: getflightbyid "
            f"flight_id={flight_id} "
            f"reason=flight_not_found_or_api_error "
            f"duration={duration:.3f}s"
        )

        return (
            f"❌ Flight not found: No flight exists with ID {flight_id}. "
            f"Please check the flight ID and try again."
        )

    logger.info(
        f"Tool successful: getflightbyid "
        f"flight_id={flight_id} duration={duration:.3f}s"
    )

    return "✈️ " + format_flight(flight)


@mcp.tool()
async def search_flights(origin: str, destination: str, date: str) -> str:
    """Search for available flights between two airports on a specific date."""
    tool_start = time.perf_counter()

    logger.info(
        f"Tool called: search_flights "
        f"origin={origin} destination={destination} date={date}"
    )

    origin = origin.upper().strip()
    destination = destination.upper().strip()
    date = date.strip()

    is_valid, error_msg = validate_search_params(origin, destination, date)

    if not is_valid:
        duration = time.perf_counter() - tool_start

        logger.warning(
            f"Tool failed validation: search_flights "
            f"origin={origin} destination={destination} date={date} "
            f"error={error_msg} duration={duration:.3f}s"
        )

        return f"❌ {error_msg}"

    if origin == destination:
        duration = time.perf_counter() - tool_start

        logger.warning(
            f"Tool failed validation: search_flights "
            f"origin={origin} destination={destination} "
            f"error=same_origin_and_destination "
            f"duration={duration:.3f}s"
        )

        return "❌ Origin and destination cannot be the same airport."

    try:
        parsed_date = datetime.strptime(date, "%Y-%m-%d").date()

    except ValueError:
        duration = time.perf_counter() - tool_start

        logger.warning(
            f"Tool failed validation: search_flights "
            f"origin={origin} destination={destination} date={date} "
            f"error=invalid_date_format duration={duration:.3f}s"
        )

        return "❌ Invalid date format. Please use YYYY-MM-DD format (e.g., 2025-12-15)."

    flights = await fetch_flights_from_api(
        origin,
        destination,
        str(parsed_date)
    )

    duration = time.perf_counter() - tool_start

    if flights is None:
        logger.error(
            f"Tool failed: search_flights "
            f"origin={origin} destination={destination} date={parsed_date} "
            f"reason=api_unavailable_or_error "
            f"duration={duration:.3f}s"
        )

        return (
            "❌ Unable to search flights: The flight service is currently unavailable. "
            "Please try again in a few moments."
        )

    if not flights:
        logger.info(
            f"Tool successful: search_flights "
            f"origin={origin} destination={destination} date={parsed_date} "
            f"flights_found=0 duration={duration:.3f}s"
        )

        return (
            f"🚫 No flights available from {origin} to {destination} on {parsed_date}.\n\n"
            f"Try searching for:\n"
            f"- A different date\n"
            f"- Nearby airports\n"
            f"- Alternative routes"
        )

    formatted_list = [format_flight(f) for f in flights]

    result = (
        f"✈️ Found {len(flights)} flight(s) from {origin} to {destination} "
        f"on {parsed_date}:\n\n"
        + "\n".join(formatted_list)
    )

    logger.info(
        f"Tool successful: search_flights "
        f"origin={origin} destination={destination} date={parsed_date} "
        f"flights_found={len(flights)} duration={duration:.3f}s"
    )

    return result


def main() -> None:
    logger.info("Running MCP server with transport=stdio")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()