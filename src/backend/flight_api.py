from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import datetime
import time
import random
import sqlite3

# Import from centralized config and db module
from config import TARGET_FLIGHTS
from db import (
    get_conn,
    init_db,
    count_flights,
    bulk_insert_flights,
    generate_more_flights,
    create_booking,
    get_booking,
    get_bookings_by_user,
    update_booking_status,
)

app = FastAPI(title="Flight API (DB-backed)")


# ---------------------------
# Startup: ensure DB + seed
# ---------------------------

@app.on_event("startup")
def startup_event() -> None:
    """Initialize database and seed flights if empty."""
    init_db()
    existing = count_flights()
    if existing < 300000:
        print(f"[flight_api] less than 300000 flights in DB, generating {TARGET_FLIGHTS} flights...")
        flights = generate_more_flights(TARGET_FLIGHTS)
        bulk_insert_flights(flights)
        print(f"[flight_api] Inserted {len(flights)} flights into DB")
    else:
        print(f"[flight_api] DB already has {existing} flights, skipping generation")


# ---------------------------
# Endpoints
# ---------------------------

@app.get("/flights")
def search_flights(
    origin: str = Query(..., min_length=3, max_length=3),
    destination: str = Query(..., min_length=3, max_length=3),
    date: str = Query(..., description="YYYY-MM-DD"),
) -> List[Dict[str, Any]]:
    """
    Search flights by origin, destination, and date.

    Example:
    GET /flights?origin=ATH&destination=LHR&date=2025-12-01
    """

    # basic date validation
    try:
        datetime.date.fromisoformat(date)
    except ValueError:
        return []

    conn = get_conn()
    try:
        cur = conn.execute(
            """
            SELECT * FROM flights
            WHERE origin = ? AND destination = ? AND date = ?
            ORDER BY price ASC
            """,
            (origin.upper(), destination.upper(), date),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    return [dict(r) for r in rows]


@app.get("/flights/{flight_id}")
def get_flight_by_id(flight_id: str) -> Dict[str, Any]:
    """
    Get a single flight by its ID.

    Example:
    GET /flights/FL-000123
    """

    conn = get_conn()
    try:
        cur = conn.execute("SELECT * FROM flights WHERE id = ?", (flight_id,))
        row = cur.fetchone()
    finally:
        conn.close()

    if row is None:
        raise HTTPException(status_code=404, detail="Flight not found")

    return dict(row)


# ---------------------------
# Booking Request Models
# ---------------------------

class BookingCreateRequest(BaseModel):
    user_id: str
    flight_id: str
    passenger_name: str
    passenger_email: str
    seats: int = 1
    status: str = "CONFIRMED"
    hold_minutes: Optional[int] = None


class BookingUpdateRequest(BaseModel):
    status: str
    cancellation_reason: Optional[str] = None


# ---------------------------
# Booking Endpoints
# ---------------------------

@app.post("/bookings")
def create_booking_endpoint(booking: BookingCreateRequest) -> Dict[str, Any]:
    """
    Create a new flight booking.
    
    Example:
    POST /bookings
    {
      "user_id": "user_001",
      "flight_id": "FL-001234",
      "passenger_name": "John Doe",
      "passenger_email": "john@example.com",
      "seats": 1,
      "status": "CONFIRMED"
    }
    """
    
    try:
        result = create_booking(
            user_id=booking.user_id,
            flight_id=booking.flight_id,
            passenger_name=booking.passenger_name,
            passenger_email=booking.passenger_email,
            seats=booking.seats,
            status=booking.status,
            hold_minutes=booking.hold_minutes
        )
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        return result
    except ValueError as e:
        # Handle insufficient seats or other validation errors
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/bookings/{booking_id}")
def get_booking_endpoint(booking_id: str) -> Dict[str, Any]:
    """
    Get a single booking by ID.
    
    Example:
    GET /bookings/BK-abc123
    """
    
    booking = get_booking(booking_id)
    
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    return booking


@app.get("/bookings")
def get_user_bookings_endpoint(user_id: str = Query(...)) -> List[Dict[str, Any]]:
    """
    Get all bookings for a specific user.
    
    Example:
    GET /bookings?user_id=user_001
    """

    
    bookings = get_bookings_by_user(user_id)
    return bookings


@app.put("/bookings/{booking_id}")
def update_booking_endpoint(
    booking_id: str,
    update: BookingUpdateRequest
) -> Dict[str, Any]:
    """
    Update a booking's status (confirm, cancel, etc).
    
    Example:
    PUT /bookings/BK-abc123
    {
      "status": "CANCELLED",
      "cancellation_reason": "Customer requested"
    }
    """
    
    result = update_booking_status(
        booking_id=booking_id,
        new_status=update.status,
        cancellation_reason=update.cancellation_reason
    )
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result


@app.delete("/bookings/{booking_id}")
def delete_booking_endpoint(booking_id: str) -> Dict[str, Any]:
    """
    Delete a booking by ID and restore the seats to the flight.
    This is used for cancellations - the booking record is completely removed.
    
    Example:
    DELETE /bookings/BK-abc123
    """
    
    from db import delete_booking
    
    success = delete_booking(booking_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    return {"success": True, "message": "Booking cancelled and seats restored"}
