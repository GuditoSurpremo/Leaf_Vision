import os
import json
from pathlib import Path
import re
import time
import logging
from typing import Tuple

# Load .env once so OPENROUTER_API_KEY is available without manual input
try:
    from dotenv import load_dotenv  # type: ignore[import-not-found]
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')
except Exception:
    pass

import requests
from requests import exceptions as req_exc
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)

OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY', '')

# Known disease labels from the local model (lowercase)
KNOWN_DISEASES = [
    # Corn
    "common rust", "gray leaf spot", "leaf blight", "healthy",
    # Potato
    "early blight", "late blight",
    # Rice
    "brown spot", "leaf blast",
    # Wheat
    "brown rust", "yellow rust",
    # Other
    "invalid",
]

SYSTEM_PROMPT = (
    "You are an agricultural assistant focused on leaf diseases and closely related crop-health topics. Maintain a formal, concise tone.\n"
    "Near-related means: symptoms, diagnosis, integrated pest management, pests/insects, environmental conditions (humidity, watering, soil, nutrients), safe handling, prevention, treatment, and model-based classification context.\n"
    "Conversation rules:\n"
    "- Use the conversation context to understand references (e.g., 'that corn', 'alternative treatment').\n"
    "- On follow-ups, DO NOT repeat the full guide/sections. Answer only what is asked.\n"
    "- Honor explicit format requests: 'paragraph' => one short paragraph; 'one sentence' => a single sentence; 'outline/bullets' => only bullet points.\n"
    "- When a disease name is provided and a FULL GUIDE is requested, respond ONLY with STRICT JSON: causes[], prevention[], treatment[], risk_factors[], short_description. No extra text. 3–5 items per list.\n"
    "- If ambiguous and no disease is provided, ask for the exact disease name in ONE short, formal sentence.\n"
    "- Be accurate. If unsure, state uncertainty and request clarification. Do not invent facts.\n"
    "- Non-JSON answers must be <= 80 words unless the user explicitly requests an outline.\n"
)

# Map category keywords to canonical section names
SECTION_MAP = {
    'prevention': ['prevention', 'preventive', 'avoidance'],
    'treatment': ['treatment', 'control', 'management'],
    'causes': ['cause', 'causes', 'etiology'],
    'risk_factors': ['risk', 'risk factor', 'risk factors']
}


def detect_outline_and_sections(msg: str):
    m = msg.lower()
    outline = any(k in m for k in ['outline', 'bullets', 'bullet points', 'bullet list', 'list of', 'make a list'])
    sections = []
    if outline:
        for key, synonyms in SECTION_MAP.items():
            for s in synonyms:
                if re.search(rf"\b{re.escape(s)}\b", m):
                    sections.append(key)
                    break
        # If no specific section mentioned, default to prevention
        if not sections:
            sections = ['prevention']
    return outline, sections


TRANSIENT_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


def _call_openrouter(payload: dict, headers: dict, max_retries: int = 2, base_delay: float = 1.5) -> Tuple[int, str, dict|None]:
    """Return (status_code, raw_text, json_or_none). Retries transient failures."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    attempt = 0
    while True:
        attempt += 1
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=45)
            txt = resp.text
            js = None
            try:
                js = resp.json()
            except Exception:
                pass
            if resp.status_code in TRANSIENT_STATUS and attempt <= max_retries:
                logger.warning("Transient upstream status %s attempt %s/%s - retrying", resp.status_code, attempt, max_retries)
                time.sleep(base_delay * attempt)
                continue
            return resp.status_code, txt, js
        except (req_exc.Timeout, req_exc.ConnectionError) as e:
            if attempt <= max_retries:
                logger.warning("Network error '%s' attempt %s/%s - retrying", e, attempt, max_retries)
                time.sleep(base_delay * attempt)
                continue
            return 599, str(e), None
        except Exception as e:  # non-network unexpected
            logger.exception("Unexpected error during upstream call")
            return 598, str(e), None


def _format_upstream_error(up_status: int, raw_text: str) -> Tuple[int, dict]:
    """Map upstream HTTP codes to local response (status_code, json_body)."""
    # Default mapping
    body = {
        "error": {
            "message": "Upstream model request failed",
            "upstream_status": up_status,
            "retryable": up_status in TRANSIENT_STATUS,
            "details": None,
        }
    }
    # Try to pull message from upstream JSON if present
    try:
        parsed = json.loads(raw_text)
        if isinstance(parsed, dict):
            # OpenRouter often wraps errors differently; attempt common keys
            msg = parsed.get('error') or parsed.get('message') or parsed.get('detail')
            if isinstance(msg, dict):
                # sometimes {message: '...'} nested
                inner = msg.get('message') or msg.get('msg') or msg.get('error')
                if isinstance(inner, str):
                    msg = inner
            if isinstance(msg, str):
                body['error']['details'] = msg[:500]
    except Exception:
        pass

    # Specific overrides
    if up_status == 401:
        body['error']['message'] = "Invalid or missing OpenRouter API key please try again"
        return status.HTTP_401_UNAUTHORIZED, body
    if up_status == 403:
        body['error']['message'] = "Access forbidden by upstream (possible model restriction)"
        return status.HTTP_403_FORBIDDEN, body
    if up_status == 404:
        body['error']['message'] = "Model or endpoint not found upstream"
        return status.HTTP_502_BAD_GATEWAY, body
    if up_status == 429:
        body['error']['message'] = "Rate limit reached. Please retry later"
        return status.HTTP_429_TOO_MANY_REQUESTS, body
    if up_status in {500, 502, 503, 504}:
        body['error']['message'] = "Upstream service is temporarily unavailable"
        # 502 for gateway style failures
        return status.HTTP_502_BAD_GATEWAY, body
    if up_status in (598, 599):
        body['error']['message'] = "Network failure contacting upstream"
        return status.HTTP_503_SERVICE_UNAVAILABLE, body

    # Other 4xx becomes Bad Gateway to keep abstraction (except ones handled above)
    if 400 <= up_status < 500:
        body['error']['message'] = "Upstream rejected the request"
        return status.HTTP_502_BAD_GATEWAY, body

    return status.HTTP_502_BAD_GATEWAY, body


@api_view(['POST'])
@permission_classes([AllowAny])
@authentication_classes([])
def chat(request):
    try:
        if not OPENROUTER_API_KEY:
            return Response({
                "error": {
                    "message": "OPENROUTER_API_KEY not set",
                    "hint": "In PowerShell: $env:OPENROUTER_API_KEY='your_key'; (setx for persistence) then restart server"
                }
            }, status=status.HTTP_400_BAD_REQUEST)
        data = request.data or {}
        user_message = data.get('message', '') or ''
        disease = data.get('disease')
        confidence = data.get('confidence')
        history = data.get('history') or []  # [{role:'user'|'assistant', content:string}]
        force_json = bool(data.get('force_json', False))

        # Normalize message for simple intent checks (greetings/thanks)
        msg_norm = ''.join(ch.lower() if ch.isalnum() or ch.isspace() else ' ' for ch in user_message).strip()

        # Greetings
        greetings = {"hi", "hello", "hey", "good morning", "good afternoon", "good evening"}
        if msg_norm in greetings or msg_norm.startswith("hello") or msg_norm.startswith("hi ") or msg_norm.startswith("hey"):
            return Response({
                "reply": "Hello. How may I assist you with leaf disease detection, causes, prevention, treatment, or risk factors?"
            })
        # Thanks
        if any(x in msg_norm for x in ["thanks", "thank you", "thankyou"]):
            return Response({"reply": "You're welcome. If you need more help with leaf diseases, please let me know."})

        # Extract disease from message if not provided
        if not disease:
            for name in KNOWN_DISEASES:
                if re.search(rf"\b{re.escape(name)}\b", msg_norm):
                    disease = name.title()
                    break

        outline_mode, outline_sections = detect_outline_and_sections(user_message)

        # Build context line for the current turn
        context_line = (
            f"Disease: {disease}. Confidence: {confidence if confidence is not None else 'N/A'}."
            if disease else
            "No disease provided. If answering a general plant-health question, reply in one short, formal paragraph (<= 80 words). If a disease name is present, return the strict JSON as instructed."
        )

        # Construct message list with conversation history
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        # Append prior turns (cap last 8 messages to limit tokens)
        if isinstance(history, list):
            for m in history[-8:]:
                r = m.get('role'); c = m.get('content')
                if r in ("user", "assistant") and isinstance(c, str) and c.strip():
                    messages.append({"role": r, "content": c.strip()[:4000]})

        fmt_instruction = ""
        if outline_mode:
            sec_text = ', '.join(outline_sections)
            fmt_instruction = (
                f"\nFORMAT: Return ONLY bullet points (lines starting with '- '), no numbering, no intro/outro. "
                f"Provide 3-7 concise phrase bullets. Focus on: {sec_text}. "
                f"If a disease name is present, keep bullets specific to it; otherwise, give general guidance for leaf diseases."
            )

        # Final user message with context
        messages.append({
            "role": "user",
            "content": f"{context_line}{fmt_instruction}\n\nUser question: {user_message or 'Provide a concise guide.'}"
        })

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": data.get('referrer', 'http://localhost'),
            "X-Title": data.get('site', 'Leaf Vision'),  # renamed fallback
        }
        payload = {
            "model": "deepseek/deepseek-chat-v3.1:free",
            "messages": messages,
            "temperature": 0.25,
            # Only force JSON when explicitly requested and not in outline mode
            "response_format": ({"type": "json_object"} if (force_json and disease and not outline_mode) else None)
        }
        if payload.get("response_format") is None:
            payload.pop("response_format")

        up_status, raw_text, js = _call_openrouter(payload, headers)
        if up_status != 200:
            mapped_status, body = _format_upstream_error(up_status, raw_text)
            return Response(body, status=mapped_status)

        # Use parsed json if available
        if not js:
            try:
                js = json.loads(raw_text)
            except Exception:
                return Response({"error": {"message": "Invalid JSON from upstream"}}, status=status.HTTP_502_BAD_GATEWAY)

        content = js.get('choices', [{}])[0].get('message', {}).get('content', '')
        if not content:
            return Response({"error": {"message": "Empty response from model"}}, status=status.HTTP_502_BAD_GATEWAY)

        if force_json and disease and not outline_mode:
            try:
                guide = json.loads(content)
                if isinstance(guide, dict):
                    return Response({"guide": guide})
            except Exception:
                # Fall back to raw text
                return Response({"reply": content})
            return Response({"reply": content})
        else:
            return Response({"reply": content})
    except Exception as e:
        logger.exception("Unhandled exception in chat view")
        return Response({"error": {"message": str(e)}}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
