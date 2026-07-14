#!/usr/bin/env python3
"""
Test script to verify Ollama is running and responding properly.
"""
import requests
import json
from pathlib import Path
from dotenv import load_dotenv
import os
import sys

# Load environment variables
ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")

print("=" * 60)
print("OLLAMA CONNECTION TEST")
print("=" * 60)
print(f"Testing Ollama at: {OLLAMA_URL}")
print(f"Model to use: {OLLAMA_MODEL}")
print()

# Test 1: Check if Ollama is reachable
print("[TEST 1] Checking if Ollama is reachable...")
try:
    response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
    print("✅ Ollama is reachable!")
    print()
except requests.exceptions.ConnectionError:
    print("❌ FAILED: Cannot connect to Ollama")
    print(f"   Make sure Ollama is running at {OLLAMA_URL}")
    print("   Run: ollama serve")
    sys.exit(1)
except Exception as e:
    print(f"❌ FAILED: {e}")
    sys.exit(1)

# Test 2: List available models
print("[TEST 2] Listing available models...")
try:
    response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
    response.raise_for_status()
    data = response.json()
    
    if not data.get("models"):
        print("⚠️  No models installed")
        print(f"   Install a model with: ollama pull {OLLAMA_MODEL}")
        sys.exit(1)
    
    models = data.get("models", [])
    print(f"✅ Found {len(models)} model(s):")
    for model in models:
        model_name = model.get("name", "Unknown")
        print(f"   - {model_name}")
    print()
    
    # Check if our target model is installed
    installed_models = [m.get("name", "").split(":")[0] for m in models]
    if not any(OLLAMA_MODEL in m for m in installed_models):
        print(f"⚠️  Model '{OLLAMA_MODEL}' is not installed")
        print(f"   Install it with: ollama pull {OLLAMA_MODEL}")
    
except Exception as e:
    print(f"❌ FAILED: {e}")
    sys.exit(1)

# Test 3: Test text generation
print("[TEST 3] Testing text generation...")
print(f"Sending prompt to {OLLAMA_MODEL}...")
try:
    response = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": OLLAMA_MODEL,
            "prompt": "What is 2+2? Answer in one word only.",
            "stream": False,
        },
        timeout=60
    )
    response.raise_for_status()
    data = response.json()
    
    generated_text = data.get("response", "").strip()
    print(f"✅ Model responded successfully!")
    print(f"   Response: {generated_text[:100]}...")
    print()
    
except requests.exceptions.Timeout:
    print(f"❌ FAILED: Request timed out (model took too long)")
    print(f"   Make sure you have enough VRAM for {OLLAMA_MODEL}")
except requests.exceptions.ConnectionError:
    print(f"❌ FAILED: Cannot connect to Ollama")
except Exception as e:
    print(f"❌ FAILED: {e}")
    sys.exit(1)

# Test 4: Test with a more complex prompt
print("[TEST 4] Testing with a complex prompt...")
try:
    response = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": OLLAMA_MODEL,
            "prompt": "You are a helpful assistant. User asks: What time is it? Give a brief response.",
            "stream": False,
        },
        timeout=60
    )
    response.raise_for_status()
    data = response.json()
    
    generated_text = data.get("response", "").strip()
    print(f"✅ Complex prompt processed successfully!")
    print(f"   Response: {generated_text[:150]}...")
    print()
    
except Exception as e:
    print(f"❌ FAILED: {e}")
    sys.exit(1)

print("=" * 60)
print("✅ ALL TESTS PASSED!")
print("=" * 60)
print(f"Ollama is running correctly on {OLLAMA_URL}")
print(f"Model '{OLLAMA_MODEL}' is responding properly")
print("You can now use the flight booking system with local Llama!")
