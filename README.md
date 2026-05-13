# AgroSight AI

AI-powered crop disease detection for farmers. Upload a plant leaf photo, get an instant diagnosis with treatment recommendations, and chat with agrovets in real time.

---

## Features

- **Disease Detection** — Upload leaf images to identify crop diseases across Corn, Potato, and Tomato (17 classes including healthy states).
- **Leaf Validation** — CNN-based leaf detector with heuristic fallback ensures only valid leaf images are processed.
- **AI Chat Assistant** — Ask follow-up questions about diagnoses, prevention, and treatment.
- **Farmer ↔ Agrovet Chat** — Real-time messaging with image, voice note, and text support.
- **Feedback Loop** — Correct misclassifications to improve the model over time.
- **Automated Retraining** — Periodic pipeline that retrains the classifier on verified feedback with safe model deployment and rollback.
- **Admin Dashboard** — Manage users, view system stats, change user passwords directly, trigger manual retraining, and roll back bad models.
- **Password Reset** — Users can request password reset tokens; admins can directly change user passwords.
- **Production-Ready Docker** — Gunicorn, Nginx, PostgreSQL, Redis, MinIO, health checks, auto-restart.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend API | Flask 3.0, SQLAlchemy, Flask-JWT-Extended |
| ML | TensorFlow 2.16 + Keras (MobileNetV2 transfer learning) |
| Database | SQLite (local dev) / PostgreSQL (production) |
| Frontend | Vanilla HTML5, CSS3, ES6 |
| Real-time Chat | Node.js + Express + Socket.IO |
| Deployment | Docker Compose, Gunicorn, Nginx |

---

## Prerequisites

- **Python 3.11** (required — TensorFlow 2.16 is not compatible with Python 3.12+)
- **Node.js 18+** (for the chat server)
- **pip** and **virtualenv**
- **Docker & Docker Compose** (for containerized deployment)

---

## Quick Start

### Local Development

```bash
# 1. Create virtual environment
python -m venv venv311
source venv311/bin/activate  # Linux/Mac
# or: venv311\Scripts\Activate.ps1  # Windows

# 2. Install dependencies
pip install -r backend/requirements.txt

# 3. Set environment variables
cp .env.example .env
# Edit .env with your settings

# 4. Run the backend
cd backend
python app.py

# 5. Run the chat server (separate terminal)
cd frontend/server
npm install
node server.js

# 6. Open frontend
# Open frontend/index.html in a browser or use Live Server
```

### Docker Deployment

```bash
# Build and start all services
docker compose up --build -d

# Check status
docker compose ps

# View logs
docker compose logs -f api

# Stop all services
docker compose down
```

The API will be available at `http://localhost:5000` and the web interface at `http://localhost:8080`.

---

## API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/health` | None | Health check |
| POST | `/api/analyze` | None | Leaf check + disease detection |
| POST | `/api/chat` | None | AI chat assistant |
| POST | `/api/auth/register` | None | Create account |
| POST | `/api/auth/login` | None | Login |
| POST | `/api/auth/admin/login` | None | Admin login |
| GET/PUT | `/api/auth/me` | JWT | Profile |
| POST | `/api/auth/change-password` | JWT | Change own password |
| POST | `/api/auth/forgot-password` | None | Request password reset |
| POST | `/api/auth/reset-password` | None | Reset password with token |
| GET | `/api/detections` | JWT | Detection history |
| POST | `/api/feedback` | None | Submit feedback |
| GET | `/api/admin/users` | Admin | List users |
| PUT | `/api/admin/users/<id>` | Admin | Update user |
| DELETE | `/api/admin/users/<id>` | Admin | Delete user |
| POST | `/api/admin/users/<id>/reset-password` | Admin | Generate temp password |
| PUT | `/api/admin/users/<id>/change-password` | Admin | Change user password directly |
| GET | `/api/admin/audit-logs` | Admin | View audit logs |

---

## AI Models

### Disease Classification
- **Architecture**: MobileNetV2 transfer learning
- **Input**: 224×224 RGB images
- **Classes**: 17 (Corn: 4, Potato: 3, Tomato: 10)
- **Accuracy**: ~89.6%
- **File**: `saved_models/best_model_finetuned.keras`

### Leaf Detection
- **Primary**: CNN binary classifier (leaf vs not-leaf)
- **Fallback**: Heuristic (green pixel + edge analysis)
- **File**: `saved_models/leaf_detector.keras` (optional)
- **Config**: `saved_models/leaf_detector_config.json`

### Training the Leaf Detector

```bash
cd backend
python -m model.train_leaf_detector --data_dir ../dataset --epochs 15
```

---

## Docker Services

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| api | Custom (Python) | 5000 | Flask + TensorFlow inference |
| chat | Custom (Node) | 5001 | Socket.IO messaging |
| web | nginx:alpine | 8080 | Static files + reverse proxy |
| postgres | postgres:16-alpine | 5432 | Database |
| minio | minio/minio | 9000/9001 | Object storage |
| redis | redis:7-alpine | 6379 | Cache/sessions |

---

## Environment Variables

Key variables (see `.env.example` for full list):

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | change-me | Flask secret key |
| `JWT_SECRET_KEY` | change-me | JWT signing key |
| `DATABASE_URL` | sqlite:///... | Database connection |
| `MODEL_PATH` | saved_models/best_model.keras | Disease model path |
| `LEAF_DETECTOR_PATH` | saved_models/leaf_detector.keras | Leaf detector path |
| `GUNICORN_WORKERS` | 2 | Gunicorn worker count |
| `GUNICORN_TIMEOUT` | 120 | Request timeout (seconds) |

---

## License

MIT