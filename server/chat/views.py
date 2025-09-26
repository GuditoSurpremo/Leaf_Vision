import os
import json
from pathlib import Path
import re

# Load .env once so OPENROUTER_API_KEY is available without manual input
try:
    from dotenv import load_dotenv  # type: ignore[import-not-found]
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')
except Exception:
    pass

import requests
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

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


@api_view(['POST'])
@permission_classes([AllowAny])
@authentication_classes([])
def chat(request):
    try:
        if not OPENROUTER_API_KEY:
            return Response({
                "error": "OPENROUTER_API_KEY is not set. In PowerShell: $env:OPENROUTER_API_KEY='your_key' and restart the server."
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

        resp = requests.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers, timeout=45)
        if resp.status_code >= 400:
            return Response({"error": resp.text}, status=status.HTTP_502_BAD_GATEWAY)
        resp_json = resp.json()
        content = resp_json.get('choices', [{}])[0].get('message', {}).get('content', '')
        if not content:
            return Response({"error": "Empty response from model."}, status=status.HTTP_502_BAD_GATEWAY)

        if force_json and disease and not outline_mode:
            try:
                guide = json.loads(content)
                if isinstance(guide, dict):
                    return Response({"guide": guide})
            except Exception:
                pass
            return Response({"reply": content})
        else:
            return Response({"reply": content})
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
