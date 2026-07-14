import os
from pathlib import Path
import logging
from datetime import datetime
from typing import Any, Dict, Optional, List
import re

import httpx
from pydantic import BaseModel, EmailStr, Field, validator
from mcp.server.fastmcp import FastMCP

# -------------------------
# MCP server init
# -------------------------

mcp = FastMCP("booking")

BOOKING_API_BASE = os.environ.get("BOOKING_API_BASE", "http://localhost:8000")


# -------------------------
# Logging setup
# -------------------------

DEFAULT_LOG_PATH = Path(__file__).parent / "booking.log"
LOG_FILE = Path(DEFAULT_LOG_PATH)

logger = logging.getLogger("booking")
logger.setLevel(logging.INFO)

if not logger.handlers:
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.INFO)

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)

logger.info("==== Booking MCP server starting ====")
logger.info(f"Logging to file: {LOG_FILE.resolve()}")
logger.info(f"Booking API base URL: {BOOKING_API_BASE}")


# -------------------------
# Validation Models
# -------------------------

class BookingValidation(BaseModel):
    """Validation model for booking inputs."""
    user_id: str = Field(..., min_length=1, max_length=100)
    flight_id: str = Field(..., pattern=r'^FL-\d{6}$')
    passenger_name: str = Field(..., min_length=2, max_length=100)
    passenger_email: EmailStr
    seats: int = Field(default=1, ge=1, le=10)
    
    @validator('passenger_name')
    def validate_name(cls, v):
        # Remove extra whitespace
        v = ' '.join(v.split())
        # Check if name contains only letters, spaces, hyphens, and apostrophes
        if not re.match(r"^[A-Za-z\s'-]+$", v):
            raise ValueError('Name must contain only letters, spaces, hyphens, and apostrophes')
        return v
    
    @validator('user_id')
    def validate_user_id(cls, v):
        if not v.strip():
            raise ValueError('User ID cannot be empty')
        return v.strip()


class BookingIdValidation(BaseModel):
    """Validation model for booking ID."""
    booking_id: str = Field(..., pattern=r'^BK-[A-F0-9]{10}$')


def validate_booking_input(
    user_id: str,
    flight_id: str,
    passenger_name: str,
    passenger_email: str,
    seats: int
) -> tuple[bool, Optional[str]]:
    """Validate booking inputs. Returns (is_valid, error_message)."""
    try:
        BookingValidation(
            user_id=user_id,
            flight_id=flight_id,
            passenger_name=passenger_name,
            passenger_email=passenger_email,
            seats=seats
        )
        return True, None
    except Exception as e:
        error_msg = str(e)
        # Make error messages user-friendly
        if "flight_id" in error_msg.lower():
            return False, "Invalid flight ID format. Flight ID should be in format FL-XXXXXX (e.g., FL-001234)."
        elif "passenger_email" in error_msg.lower():
            return False, "Invalid email address format. Please provide a valid email."
        elif "passenger_name" in error_msg.lower():
            return False, "Invalid passenger name. Name should contain only letters, spaces, hyphens, and apostrophes."
        elif "seats" in error_msg.lower():
            return False, "Invalid number of seats. Please specify between 1 and 10 seats."
        elif "user_id" in error_msg.lower():
            return False, "Invalid user ID provided."
        else:
            return False, f"Validation error: {error_msg}"


def validate_booking_id(booking_id: str) -> tuple[bool, Optional[str]]:
    """Validate booking ID format. Returns (is_valid, error_message)."""
    try:
        BookingIdValidation(booking_id=booking_id)
        return True, None
    except Exception:
        return False, "Invalid booking ID format. Booking ID must be in format BK-XXXXXXXXXX (e.g., BK-97C72D61EF)."


# -------------------------
# API Helper Functions
# -------------------------

async def create_booking_via_api(
    user_id: str,
    flight_id: str,
    passenger_name: str,
    passenger_email: str,
    seats: int,
    status: str = "CONFIRMED",
    hold_minutes: Optional[int] = None
) -> Dict[str, Any]:
    """Call the booking API to create a new booking."""
    url = f"{BOOKING_API_BASE}/bookings"
    
    payload = {
        "user_id": user_id,
        "flight_id": flight_id,
        "passenger_name": passenger_name,
        "passenger_email": passenger_email,
        "seats": seats,
        "status": status,
    }
    
    if hold_minutes is not None:
        payload["hold_minutes"] = hold_minutes
    
    try:
        logger.info(
            "Creating booking via API",
            extra={
                "action": "create_booking",
                "user_id": user_id,
                "flight_id": flight_id,
                "seats": seats,
                "status": status
            }
        )
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=10.0)
            response.raise_for_status()
            result = response.json()
            logger.info(
                "Booking created successfully",
                extra={
                    "action": "create_booking_success",
                    "booking_id": result.get('id'),
                    "user_id": user_id
                }
            )
            return result
    except httpx.HTTPStatusError as e:
        logger.error(
            "HTTP error creating booking",
            extra={
                "action": "create_booking_error",
                "status_code": e.response.status_code,
                "user_id": user_id
            }
        )
        return {"error": "Unable to create booking. The booking service is currently unavailable. Please try again later."}
    except httpx.TimeoutException:
        logger.error(
            "Timeout creating booking",
            extra={"action": "create_booking_timeout", "user_id": user_id}
        )
        return {"error": "Booking request timed out. Please try again."}
    except Exception as e:
        logger.exception(
            "Unexpected error creating booking",
            extra={"action": "create_booking_exception", "user_id": user_id}
        )
        return {"error": "An unexpected error occurred while creating your booking. Please contact support."}


async def get_booking_via_api(booking_id: str) -> Optional[Dict[str, Any]]:
    """Call the booking API to get a single booking."""
    url = f"{BOOKING_API_BASE}/bookings/{booking_id}"
    
    try:
        logger.info(
            "Getting booking via API",
            extra={"action": "get_booking", "booking_id": booking_id}
        )
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10.0)
            if response.status_code == 404:
                logger.info(
                    "Booking not found",
                    extra={"action": "get_booking_not_found", "booking_id": booking_id}
                )
                return None
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        logger.error(
            "HTTP error getting booking",
            extra={
                "action": "get_booking_error",
                "status_code": e.response.status_code,
                "booking_id": booking_id
            }
        )
        return None
    except Exception as e:
        logger.exception(
            "Unexpected error getting booking",
            extra={"action": "get_booking_exception", "booking_id": booking_id}
        )
        return None


async def get_user_bookings_via_api(user_id: str) -> List[Dict[str, Any]]:
    """Call the booking API to get all bookings for a user USING the user ID."""
    url = f"{BOOKING_API_BASE}/bookings"
    
    try:
        logger.info(
            "Getting user bookings via API",
            extra={"action": "get_user_bookings", "user_id": user_id}
        )
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params={"user_id": user_id}, timeout=10.0)
            response.raise_for_status()
            bookings = response.json()
            logger.info(
                "User bookings retrieved",
                extra={
                    "action": "get_user_bookings_success",
                    "user_id": user_id,
                    "count": len(bookings) if isinstance(bookings, list) else 0
                }
            )
            return bookings
    except httpx.HTTPStatusError as e:
        logger.error(
            "HTTP error getting user bookings",
            extra={
                "action": "get_user_bookings_error",
                "status_code": e.response.status_code,
                "user_id": user_id
            }
        )
        return []
    except Exception as e:
        logger.exception(
            "Unexpected error getting user bookings",
            extra={"action": "get_user_bookings_exception", "user_id": user_id}
        )
        return []


async def update_booking_via_api(
    booking_id: str,
    status: str,
    cancellation_reason: Optional[str] = None
) -> Dict[str, Any]:
    """Call the booking API to update a booking's status."""
    url = f"{BOOKING_API_BASE}/bookings/{booking_id}"
    
    payload = {"status": status}
    if cancellation_reason:
        payload["cancellation_reason"] = cancellation_reason
    
    try:
        logger.info(
            "Updating booking via API",
            extra={
                "action": "update_booking",
                "booking_id": booking_id,
                "new_status": status
            }
        )
        async with httpx.AsyncClient() as client:
            response = await client.put(url, json=payload, timeout=10.0)
            response.raise_for_status()
            result = response.json()
            logger.info(
                "Booking updated successfully",
                extra={
                    "action": "update_booking_success",
                    "booking_id": booking_id,
                    "new_status": status
                }
            )
            return result
    except httpx.HTTPStatusError as e:
        logger.error(
            "HTTP error updating booking",
            extra={
                "action": "update_booking_error",
                "status_code": e.response.status_code,
                "booking_id": booking_id
            }
        )
        return {"error": "Unable to update booking. The booking service is currently unavailable. Please try again later."}
    except httpx.TimeoutException:
        logger.error(
            "Timeout updating booking",
            extra={"action": "update_booking_timeout", "booking_id": booking_id}
        )
        return {"error": "Booking update request timed out. Please try again."}
    except Exception as e:
        logger.exception(
            "Unexpected error updating booking",
            extra={"action": "update_booking_exception", "booking_id": booking_id}
        )
        return {"error": "An unexpected error occurred while updating your booking. Please contact support."}


async def delete_booking_via_api(booking_id: str) -> Dict[str, Any]:
    """Call the booking API to delete a booking (used for cancellations)."""
    url = f"{BOOKING_API_BASE}/bookings/{booking_id}"
    
    try:
        logger.info(
            "Deleting booking via API",
            extra={
                "action": "delete_booking",
                "booking_id": booking_id
            }
        )
        async with httpx.AsyncClient() as client:
            response = await client.delete(url, timeout=10.0)
            response.raise_for_status()
            result = response.json()
            logger.info(
                "Booking deleted successfully",
                extra={
                    "action": "delete_booking_success",
                    "booking_id": booking_id
                }
            )
            return result
    except httpx.HTTPStatusError as e:
        logger.error(
            "HTTP error deleting booking",
            extra={
                "action": "delete_booking_error",
                "status_code": e.response.status_code,
                "booking_id": booking_id
            }
        )
        if e.response.status_code == 404:
            return {"error": "❌ Booking not found. It may have already been cancelled."}
        return {"error": "❌ Unable to cancel booking. The booking service is currently unavailable. Please try again later."}
    except httpx.TimeoutException:
        logger.error(
            "Timeout deleting booking",
            extra={"action": "delete_booking_timeout", "booking_id": booking_id}
        )
        return {"error": "❌ Booking cancellation request timed out. Please try again."}
    except Exception as e:
        logger.exception(
            "Unexpected error deleting booking",
            extra={"action": "delete_booking_exception", "booking_id": booking_id}
        )
        return {"error": "❌ An unexpected error occurred while cancelling your booking. Please contact support."}


# -------------------------
# Helpers
# -------------------------

def format_booking(booking: Dict[str, Any]) -> str:
    """
    Turn a booking row into a human-readable string.
    """
    from datetime import datetime
    
    name = booking.get("passenger_name", "Unknown Passenger")
    email = booking.get("passenger_email", "unknown@example.com")
    status = booking.get('status', 'UNKNOWN')
    
    # Format status with emoji
    status_emoji = {
        'CONFIRMED': '✅',
        'HELD': '⏳',
        'CANCELLED': '❌'
    }.get(status, '❓')
    
    # Format dates
    created_at = booking.get('created_at', '')
    if created_at:
        try:
            dt = datetime.fromisoformat(created_at.replace('Z', ''))
            created_at = dt.strftime('%B %d, %Y at %I:%M %p')
        except:
            pass
    
    hold_expires_at = booking.get("hold_expires_at")
    hold_line = ""
    if hold_expires_at:
        try:
            dt = datetime.fromisoformat(hold_expires_at.replace('Z', ''))
            hold_expires_at = dt.strftime('%B %d, %Y at %I:%M %p')
            hold_line = f"  ⏰ Hold Expires: {hold_expires_at}\n"
        except:
            hold_line = f"  ⏰ Hold Expires: {hold_expires_at}\n"

    return (
        f"🎫 **Booking {booking.get('id', 'UNKNOWN')}**\n"
        f"  ✈️ Flight: {booking.get('flight_id', 'UNKNOWN')}\n"
        f"  👤 Passenger: {name}\n"
        f"  📧 Email: {email}\n"
        f"  💺 Seats: {booking.get('seats', '?')}\n"
        f"  {status_emoji} Status: {status}\n"
        f"{hold_line}"
        f"  📅 Booked: {created_at}"
    ).rstrip()


# -------------------------
# MCP tools
# -------------------------

@mcp.tool()
async def book_flight(
    user_id: str,
    flight_id: str,
    passenger_name: str,
    passenger_email: str,
    seats: int = 1,
) -> str:
    """
    Create a CONFIRMED booking for a given flight id and user id.
    """
    logger.info(
        "book_flight tool called",
        extra={
            "tool": "book_flight",
            "user_id": user_id,
            "flight_id": flight_id,
            "seats": seats
        }
    )

    # Validate inputs
    is_valid, error_msg = validate_booking_input(
        user_id, flight_id, passenger_name, passenger_email, seats
    )
    if not is_valid:
        logger.warning(
            "Booking validation failed",
            extra={"tool": "book_flight", "error": error_msg}
        )
        return f"❌ Validation Error: {error_msg}"

    booking = await create_booking_via_api(
        user_id=user_id,
        flight_id=flight_id,
        passenger_name=passenger_name,
        passenger_email=passenger_email,
        seats=seats,
        status="CONFIRMED",
    )
    
    if "error" in booking:
        error_msg = booking['error']
        # Check if it's a seat availability error
        if "enough seats" in error_msg.lower() or "seats remaining" in error_msg.lower():
            return f"❌ {error_msg}"
        return f"❌ Booking Failed: {error_msg}"

    return "✅ Booking Confirmed!\n\n" + format_booking(booking)


@mcp.tool()
async def hold_flight(
    user_id: str,
    flight_id: str,
    passenger_name: str,
    passenger_email: str,
    seats: int = 1,
    hold_minutes: int = 30,
) -> str:
    """
    Create a HELD booking (a temporary hold) for a given flight and user.
    """
    logger.info(
        "hold_flight tool called",
        extra={
            "tool": "hold_flight",
            "user_id": user_id,
            "flight_id": flight_id,
            "seats": seats,
            "hold_minutes": hold_minutes
        }
    )

    # Validate inputs
    is_valid, error_msg = validate_booking_input(
        user_id, flight_id, passenger_name, passenger_email, seats
    )
    if not is_valid:
        logger.warning(
            "Hold validation failed",
            extra={"tool": "hold_flight", "error": error_msg}
        )
        return f"❌ Validation Error: {error_msg}"

    if hold_minutes <= 0 or hold_minutes > 1440:  # Max 24 hours
        return "❌ Invalid hold duration. Please specify between 1 and 1440 minutes (24 hours)."

    booking = await create_booking_via_api(
        user_id=user_id,
        flight_id=flight_id,
        passenger_name=passenger_name,
        passenger_email=passenger_email,
        seats=seats,
        status="HELD",
        hold_minutes=hold_minutes,
    )
    
    if "error" in booking:
        error_msg = booking['error']
        # Check if it's a seat availability error
        if "enough seats" in error_msg.lower() or "seats remaining" in error_msg.lower():
            return f"❌ {error_msg}"
        return f"❌ Hold Failed: {error_msg}"

    return "✅ Flight Hold Created!\n\n" + format_booking(booking)


@mcp.tool()
async def confirm_held_booking(booking_id: str, user_id: str) -> str:
    """
    Turn a HELD booking into a CONFIRMED booking (only your own bookings).
    """
    logger.info(
        "confirm_held_booking tool called",
        extra={"tool": "confirm_held_booking", "booking_id": booking_id, "user_id": user_id}
    )

    # Validate booking ID format
    is_valid, error_msg = validate_booking_id(booking_id)
    if not is_valid:
        logger.warning(
            "Invalid booking ID format",
            extra={"tool": "confirm_held_booking", "booking_id": booking_id}
        )
        return f"❌ {error_msg}"

    booking = await get_booking_via_api(booking_id)
    if booking is None:
        logger.warning(
            "Booking not found",
            extra={"tool": "confirm_held_booking", "booking_id": booking_id}
        )
        return f"❌ No booking found with ID {booking_id}. Please check the booking ID and try again."

    # Verify ownership
    booking_owner = booking.get("user_id")
    if booking_owner != user_id:
        logger.warning(
            "Unauthorized confirmation attempt",
            extra={
                "tool": "confirm_held_booking",
                "booking_id": booking_id,
                "requesting_user": user_id,
                "booking_owner": booking_owner
            }
        )
        return f"❌ Access Denied: You don't have permission to confirm this booking. This booking belongs to a different user."

    if booking.get("status") != "HELD":
        return f"❌ Cannot confirm: Booking {booking_id} is not on hold (current status: {booking.get('status')})."

    # Check hold expiry if present
    hold_expires_at = booking.get("hold_expires_at")
    if hold_expires_at:
        try:
            expires_dt = datetime.fromisoformat(hold_expires_at.replace("Z", ""))
            if datetime.utcnow() > expires_dt:
                logger.info(
                    "Hold expired",
                    extra={"tool": "confirm_held_booking", "booking_id": booking_id}
                )
                # Delete the expired hold booking
                await delete_booking_via_api(booking_id)
                return (
                    f"❌ Hold Expired: The hold for booking {booking_id} has expired and has been automatically cancelled. Seats have been restored."
                )
        except Exception:
            # Ignore parsing issues; best effort only
            pass

    updated = await update_booking_via_api(booking_id, "CONFIRMED")
    if "error" in updated:
        return f"❌ Confirmation Failed: {updated['error']}"

    logger.info(
        "Booking confirmed successfully",
        extra={"tool": "confirm_held_booking", "booking_id": booking_id, "user_id": user_id}
    )
    return "✅ Booking Confirmed!\n\n" + format_booking(updated)


@mcp.tool()
async def cancel_booking(booking_id: str, user_id: str, reason: Optional[str] = None) -> str:
    """
    Cancel an existing booking (only your own bookings).
    """
    logger.info(
        "cancel_booking tool called",
        extra={
            "tool": "cancel_booking",
            "booking_id": booking_id,
            "user_id": user_id,
            "reason": reason
        }
    )

    # Validate booking ID format
    is_valid, error_msg = validate_booking_id(booking_id)
    if not is_valid:
        logger.warning(
            "Invalid booking ID format",
            extra={"tool": "cancel_booking", "booking_id": booking_id}
        )
        return f"❌ {error_msg}"

    booking = await get_booking_via_api(booking_id)
    if booking is None:
        logger.warning(
            "Booking not found",
            extra={"tool": "cancel_booking", "booking_id": booking_id}
        )
        return f"❌ No booking found with ID {booking_id}. Please check the booking ID and try again."

    # Verify ownership
    booking_owner = booking.get("user_id")
    if booking_owner != user_id:
        logger.warning(
            "Unauthorized cancellation attempt",
            extra={
                "tool": "cancel_booking",
                "booking_id": booking_id,
                "requesting_user": user_id,
                "booking_owner": booking_owner
            }
        )
        return f"❌ Access Denied: You don't have permission to cancel this booking. This booking belongs to a different user."

    current_status = booking.get("status")

    # Delete the booking (this will also restore seats to the flight)
    result = await delete_booking_via_api(booking_id)
    if "error" in result:
        return f"❌ Cancellation Failed: {result['error']}"

    logger.info(
        "Booking cancelled and deleted successfully",
        extra={
            "tool": "cancel_booking",
            "booking_id": booking_id,
            "user_id": user_id,
            "previous_status": current_status,
            "reason": reason
        }
    )
    
    # Format a confirmation message with the booking details that were cancelled
    cancellation_info = f"""✅ Booking Cancelled Successfully!

Booking ID: {booking_id}
Flight: {booking.get('flight_id')}
Passenger: {booking.get('passenger_name')}
Seats: {booking.get('seats')}
Previous Status: {current_status}
"""
    if reason:
        cancellation_info += f"Cancellation Reason: {reason}\n"
    
    cancellation_info += "\nThe booking has been removed and seats have been restored to the flight."
    
    return cancellation_info


@mcp.tool()
async def get_booking_details(booking_id: str, user_id: str) -> str:
    """
    Retrieve details of a booking by its ID (only your own bookings).
    """
    logger.info(
        "get_booking_details tool called",
        extra={"tool": "get_booking_details", "booking_id": booking_id, "user_id": user_id}
    )

    # Validate booking ID format
    is_valid, error_msg = validate_booking_id(booking_id)
    if not is_valid:
        logger.warning(
            "Invalid booking ID format",
            extra={"tool": "get_booking_details", "booking_id": booking_id}
        )
        return f"❌ {error_msg}"

    booking = await get_booking_via_api(booking_id)
    if booking is None:
        logger.warning(
            "Booking not found",
            extra={"tool": "get_booking_details", "booking_id": booking_id}
        )
        return f"❌ No booking found with ID {booking_id}. Please check the booking ID and try again."

    # Verify ownership
    booking_owner = booking.get("user_id")
    if booking_owner != user_id:
        logger.warning(
            "Unauthorized access attempt",
            extra={
                "tool": "get_booking_details",
                "booking_id": booking_id,
                "requesting_user": user_id,
                "booking_owner": booking_owner
            }
        )
        return f"❌ Access Denied: You don't have permission to view this booking. This booking belongs to a different user."

    return format_booking(booking)


@mcp.tool()
async def get_user_bookings(user_id: str) -> str:
    """
    Retrieve all bookings for a given user ID.
    Use this when the user asks about "my bookings", "my reservations", or "my flights".
    The user_id should be the logged-in user's ID from the user context.
    """
    logger.info(
        "get_user_bookings tool called",
        extra={"tool": "get_user_bookings", "user_id": user_id}
    )

    # Validate user_id is not empty
    if not user_id or not user_id.strip():
        return "❌ User ID cannot be empty."

    user_bookings = await get_user_bookings_via_api(user_id)

    if not user_bookings:
        logger.info(
            "No bookings found for user",
            extra={"tool": "get_user_bookings", "user_id": user_id}
        )
        return f"📭 No bookings found for user {user_id}. You haven't made any flight bookings yet."

    lines = [
        f"{i+1}. {format_booking(b)}"
        for i, b in enumerate(user_bookings)
    ]
    return "\n\n".join(lines)


# -------------------------
# Entry point
# -------------------------

def main() -> None:
    logger.info("Running Booking MCP server (transport=stdio)")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
