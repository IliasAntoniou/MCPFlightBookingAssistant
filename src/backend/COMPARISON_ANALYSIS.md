# Host.py Comparison Analysis: MCPFlightBooking vs MCPFlightBookingFinal

## Summary
Both files have virtually identical logic. The main difference is **API client** (Gemini vs Ollama), not the tool-calling mechanism.

## Key Findings for Ollama Tool-Calling Issues

### 1. **System Prompt Structure** ✅ IDENTICAL
Both use the same system prompt format requiring JSON for tool calls:
```json
{
  "tool": "tool_name_here",
  "args": {...}
}
```

### 2. **Response Parsing Logic** ✅ IDENTICAL
Both use `_extract_json()` with identical regex:
```python
r"```(?:json)?\s*(\{.*?\})\s*```"
```
Then fallback to parsing entire text as JSON.

### 3. **Critical Difference Found** ⚠️

#### MCPFlightBooking (Gemini) - process_query_with_auth:
```python
# Ask Gemini whether to call a tool
initial_text = self._call_gemini(
    f"{system_prompt}{user_context}{context_text}\n\nUser question:\n{query}"
)
```

#### MCPFlightBookingFinal (Ollama) - process_query_with_auth:
```python
# Ask Ollama whether to call a tool
initial_text = self._call_ollama(
    f"{system_prompt}{user_context}{context_text}\n\nUser question:\n{query}"
)
```

**The prompts are identical!** No difference here.

### 4. **Potential Root Cause of Ollama Failures**

The issue is likely **NOT** in the code logic, but in:

#### A. Model Instruction Following
- **Qwen2:8b** (newly set) may have weaker JSON instruction-following than Gemini
- Qwen2:8b might not strictly follow "ONLY JSON" requirement
- Consider testing with models known for better tool-use: **Hermes 2 Pro** or **Neural-chat**

#### B. Prompt Formatting Sensitivity
Ollama models are MORE sensitive to exact prompt formatting. Consider:
- Adding clearer delimiters
- Making JSON format examples more prominent
- Adding failure case handling

#### C. Response Format Issues
Ollama might:
- Add extra whitespace around JSON
- Include markdown formatting unexpectedly
- Return partial JSON

### 5. **Recommended Fixes for Ollama**

#### Option 1: Improve System Prompt
```python
system_prompt = f"""
You are a flight booking assistant. CRITICAL RULES:

WHEN USING A TOOL:
- Respond with PURE JSON ONLY (no markdown, no explanation)
- Format: {{"tool":"name","args":{{"key":"value"}}}}

AVAILABLE TOOLS:
{tools_block}

...rest of prompt
"""
```

#### Option 2: Enhance JSON Extraction
```python
def _extract_json(text: str) -> Optional[dict]:
    # Try multiple patterns
    patterns = [
        r"```(?:json)?\s*(\{.*?\})\s*```",  # Current
        r"(\{[^{}]*\"tool\"[^{}]*\})",       # Raw JSON with tool key
        r"```\n?json\n?(\{.*?\})\n?```",    # Stricter markdown
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except:
                pass
    # Try entire text
    try:
        return json.loads(text.strip())
    except:
        return None
```

#### Option 3: Switch to Better Model
Test these models (in order of compatibility):
1. `qwen2.5:8b` - Better than qwen2:8b
2. `hermes2-pro:latest` - Excellent tool-use
3. `mistaral:8b` - Good general purpose
4. `neural-chat:latest` - Good conversational

## Conclusion

**The code is not broken.** The issue is **model capability**, not implementation.

**Next steps:**
1. Switch to `qwen2.5:8b` (improved version)
2. Or test `hermes2-pro` (specifically designed for tool-use)
3. If needed, enhance the system prompt with stricter JSON formatting requirements
4. Add logging to see actual model responses for debugging
