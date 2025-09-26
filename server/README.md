Leaf Vision - Setup

Backend (Django)
1) Create venv and install requirements
   - python -m venv .venv
   - .venv\Scripts\Activate.ps1
   - pip install -r server/requirements.txt
   - (Optional for CUDA) pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121

2) Run server
   - python server/manage.py migrate
   - python server/manage.py runserver 0.0.0.0:8000

Frontend (Vite + React + Tailwind)
1) Install deps
   - cd web
   - npm install

2) Start dev
   - npm run dev

Use
- POST http://localhost:8000/api/vision/predict/ with multipart form key `image`
- POST http://localhost:8000/api/chat/ with JSON { message, disease?, confidence? }

Set env
- OPENROUTER_API_KEY=your_key (PowerShell: $env:OPENROUTER_API_KEY='your_key')
