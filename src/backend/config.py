"""
Centralized configuration for the flight booking application.
"""

import datetime
from pathlib import Path

# ---------------------------
# Database Configuration
# ---------------------------

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "flight_app.db"

# ---------------------------
# Flights Generation Config
# ---------------------------

AIRPORTS = [
    "ATH", "LHR", "CDG", "FRA", "AMS", "MAD", "BCN", "MUC", "ZRH", "VIE",
    "ROM", "BER", "DUB", "CPH", "ARN", "OSL", "HEL", "IST", "PRG", "BUD"
]

AIRLINES = [
    "Hellas Air",
    "EuroSky",
    "Global Wings",
    "SkyLink",
    "Air Continental",
    "BlueJet",
]

BASE_DATE = datetime.date(2026, 5, 9)
NUM_DAYS = 30              # how many days forward to generate
TARGET_FLIGHTS = 100_000   # total number of flights to generate
