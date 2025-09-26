# Leaf Vision

 AI web app for plant leaf disease identification + agronomy assistant (Vision Transformer inference + DeepSeek chat guidance). Educational decision‑support only (not a certified diagnostic tool).

---

## 1. Features

- Vision Transformer (ViT) multi‑crop disease classifier (corn, potato, rice, wheat, etc.)
- Top‑k predictions with confidence
- Structured guidance: causes / prevention / treatment / risk factors
- Conversational assistant (DeepSeek via OpenRouter)
- Clean responsive UI (glass cards, dark mode)
- Single unified Python virtual environment (simple deployment)
- Safe fallback if WebSockets (Django Channels) not installed
- Privacy aware: images processed then discarded (configurable)

---

## 2. Tech Stack

| Layer      | Stack |
|------------|-------|
| Frontend   | React + TypeScript + Vite (Node 18+) |
| Styling    | Utility / custom CSS, gradients |
| Backend    | Python (Django or FastAPI style endpoints) |
| Inference  | Fine‑tuned ViT (PyTorch) |
| Chat       | OpenRouter (DeepSeek model) |
| Optional   | Docker / GitHub Actions |

---

## 3. Prerequisites

Install first (Windows / macOS / Linux):

- Python 3.10+  
- Node.js 18+ (includes npm)  
- Git  
- (Optional) CUDA-capable GPU + torch w/ CUDA for speed  
- (Optional) curl (for quick API tests)  

---

## 4. Repository Layout (Simplified)

```
Leaf Vision/
├─ server/                 # Backend (API, settings, prediction, chat)
│  ├─ api/
│  ├─ chat/consumers.py    # Safe if channels absent
│  ├─ models/leaf_vit.pt   # Place model weights here (see section 8)
│  └─ manage.py (if Django) or main.py (FastAPI)
├─ web/
│  ├─ src/pages/App.tsx
│  ├─ src/assets/DeepSeek.jpg
│  └─ index.html
├─ .venv/                  # Single virtual environment (NOT committed)
├─ requirements.txt        # Locked backend + ML dependencies
├─ package.json (frontend under web/)
└─ README.md
```

---

## 5. Environment Setup (Single venv at project root)

PowerShell (Windows):
```powershell
cd "c:\Leaf Vision"
python -m venv .venv
. .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

macOS / Linux:
```bash
cd Leaf\ Vision
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 6. Frontend Install

```bash
cd web
npm install
npm run dev
# Dev URL: http://localhost:5173
```

---

## 7. Backend Run (choose one)

Django example:
```bash
cd server
python manage.py migrate
python manage.py runserver 8000
# http://127.0.0.1:8000
```

FastAPI (if used):
```bash
cd server
uvicorn main:app --reload --port 8000
```

---

## 8. Model Weights

Options:
1. Local file: place `leaf_vit.pt` under `server/models/`
2. Download on first run: add code to fetch from a release / Hugging Face
3. Large file policy: use Git LFS or provide manual download instructions

Example (manual copy):
```
server/models/leaf_vit.pt
```

---

## 9. Environment Variables

Create `server/.env` (DO NOT commit secrets):

```
OPENROUTER_API_KEY=sk-your-key
OPENROUTER_BASE=https://openrouter.ai/api/v1
VISION_MODEL_PATH=./server/models/leaf_vit.pt
ALLOW_ORIGINS=http://localhost:5173
DEBUG=True
```

Frontend `web/.env`:
```
VITE_API_BASE=http://127.0.0.1:8000
VITE_CHAT_ENABLED=true
VITE_APP_NAME="Leaf Vision"
```

Restart services after changes.

---

## 10. API Examples

Prediction:
```bash
curl -F "file=@sample_leaf.jpg" http://127.0.0.1:8000/api/predict
```

Sample response:
```json
{
  "label": "early_blight",
  "confidence": 0.94,
  "top": [
    {"label":"early_blight","confidence":0.94},
    {"label":"leaf_spot","confidence":0.03}
  ],
  "guide": {
    "short_description": "...",
    "prevention": ["Rotate crops", "Remove infected debris"]
  }
}
```

Chat:
```bash
curl -H "Content-Type: application/json" -d '{
  "messages":[{"role":"user","content":"How to prevent early blight?"}],
  "context":{"prediction":"early_blight"}
}' http://127.0.0.1:8000/api/chat
```

---

## 11. Typical Workflow

1. Activate venv  
2. Start backend (loads ViT model once)  
3. Start frontend (Vite dev server)  
4. Open browser → upload leaf image → view prediction + confidence  
5. Open chat → ask follow‑ups (treatment / prevention steps)  
6. Use About modal for quick model overview  

---

## 12. Production Build

Frontend:
```bash
cd web
npm run build
# Output: web/dist
```

Serve `dist/` (Nginx, static host, or Django static).  

Backend (Django):
```
DEBUG=False
ALLOWED_HOSTS=your.domain
python manage.py collectstatic
gunicorn yourproject.wsgi:application
```

---

## 13. Recommended .gitignore (key entries)

```
.venv/
node_modules/
dist/
__pycache__/
*.pyc
.env
server/.env
db.sqlite3
*.log
```

---

## 14. Troubleshooting

| Issue | Fix |
|-------|-----|
| Module not found | Ensure venv activated |
| CORS error | Add frontend origin to ALLOW_ORIGINS |
| Slow first request | Warm model at startup (dummy inference) |
| Chat 401 | Check OPENROUTER_API_KEY |
| Missing model | Confirm VISION_MODEL_PATH correct |

Check dependency health:
```bash
pip check
```

---

## 15. Security / Privacy

- Do not expose API key in frontend bundle
- Set `DEBUG=False` before public deploy
- Optionally hash / anonymize file names
- Add rate limiting for public endpoints

---

## 16. Contributing

1. Fork & clone  
2. Create branch: `feat/your-feature`  
3. Commit (conventional messages)  
4. PR with concise description  

---

## 17. License

[MIT License](LICENSE).

---

## 18. Disclaimer
