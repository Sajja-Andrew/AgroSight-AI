# AgroSight AI

AI-powered crop disease detection for farmers. Upload a plant leaf photo, get an instant diagnosis with treatment recommendations, and chat with agrovets in real time.

---

## Features

- **Disease Detection** â€” Upload leaf images to identify crop diseases across Corn, Potato, and Tomato (17 classes including healthy states).
- **AI Chat Assistant** â€” Ask follow-up questions about diagnoses, prevention, and treatment.
- **Farmer â†” Agrovet Chat** â€” Real-time messaging with image, voice note, and text support.
- **Feedback Loop** â€” Correct misclassifications to improve the model over time.
- **Automated Retraining** â€” Periodic pipeline that retrains the classifier on verified feedback with safe model deployment and rollback.
- **Admin Dashboard** â€” Manage users, view system stats, trigger manual retraining, and roll back bad models.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend API | Flask 3.0, SQLAlchemy, Flask-JWT-Extended |
| ML | TensorFlow 2.16 + Keras (MobileNetV2 transfer learning) |
| Database | SQLite (local dev) / PostgreSQL (Render production) |
| Frontend | Vanilla HTML5, CSS3, ES6 |
| Real-time Chat | Node.js + Express + Socket.IO |
| Deployment | Docker, Render, Gunicorn |

---

## Prerequisites

- **Python 3.11** (required â€” TensorFlow 2.16 is not compatible with Python 3.12+)
- **Node.js 18+** (for the chat server)
- **pip** and **virtualenv**

---

## Project Structure

```
AgroSight AI_ai/
â”œâ”€â”€ backend/               # Flask API + ML pipeline
â”‚   â”œâ”€â”€ app.py             # Main application entrypoint
â”‚   â”œâ”€â”€ config.py          # Centralized configuration
â”‚   â”œâ”€â”€ database.py        # SQLAlchemy models
â”‚   â”œâ”€â”€ model_loader.py    # Keras model loading
â”‚   â”œâ”€â”€ pipeline/          # Feedback retraining pipeline
â”‚   â”œâ”€â”€ model/             # Training + inference code
â”‚   â””â”€â”€ requirements.txt
â”œâ”€â”€ frontend/              # Static HTML/CSS/JS
â”‚   â”œâ”€â”€ index.html
â”‚   â”œâ”€â”€ farmer-dashboard.html
â”‚   â”œâ”€â”€ agrovet-dashboard.html
â”‚   â”œâ”€â”€ admin-dashboard.html
â”‚   â”œâ”€â”€ css/
â”‚   â””â”€â”€ js/
â”œâ”€â”€ frontend/server/       # Node.js Socket.IO chat server
â”‚   â””â”€â”€ server.js
â”œâ”€â”€ dataset/               # Training images
â”‚   â”œâ”€â”€ color/             # Raw images (17 classes)
â”‚   â””â”€â”€ processed/         # train/val/test splits
â”œâ”€â”€ saved_models/          # Trained Keras models + registry
â””â”€â”€ render.yaml            # Render.com blueprint
```

---

## Local Setup

### 1. Clone and enter the project

```bash
git clone <repo-url>
cd AgroSight AI_ai
```

### 2. Backend (Flask API)

```bash
cd backend

# Create a Python 3.11 virtual environment
python3.11 -m venv venv311
source venv311/bin/activate      # Linux/Mac
# or: venv311\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Start the Flask dev server
python app.py
```

The API will be available at `http://localhost:5000`.

### 3. Chat Server (Node.js)

```bash
cd frontend/server

npm install
node server.js
```

The chat server will be available at `http://localhost:5001`.

### 4. Frontend

Open `frontend/index.html` directly in a browser, or serve it with any static file server:

```bash
cd frontend
python -m http.server 8080
```

Then navigate to `http://localhost:8080`.

---

## Environment Variables

All configuration is loaded from environment variables with sensible defaults.

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | `AgroSightAI-dev-secret-change-in-production` | Flask secret key |
| `JWT_SECRET_KEY` | same as `SECRET_KEY` | JWT signing key |
| `DATABASE_URL` | `sqlite:///<backend>/AgroSightAI.db` | SQLAlchemy database URI |
| `MODEL_PATH` | `<project>/saved_models/best_model.keras` | Disease model file |
| `CLASS_INDICES_PATH` | `<project>/saved_models/class_indices.json` | Class mapping |
| `CORS_ORIGINS` | `http://localhost:5000,http://127.0.0.1:5000` | Allowed frontend origins |
| `UPLOAD_FOLDER` | `<backend>/uploads` | Image upload directory |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `RETRAIN_SCHEDULE` | `weekly` | Pipeline schedule: `weekly`, `monthly`, or `off` |
| `MIN_FEEDBACK_COUNT` | `5` | Minimum feedback entries to trigger retraining |
| `IMPROVEMENT_THRESHOLD` | `0.01` | Minimum accuracy improvement to promote a new model |

**For production, always set `SECRET_KEY`, `JWT_SECRET_KEY`, and `CORS_ORIGINS`.**

---

## API Endpoints

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/auth/register` | Create account (farmer or agrovet) |
| `POST` | `/api/auth/login` | Login with email/username/phone |
| `POST` | `/api/auth/admin/login` | Admin login |
| `GET`  | `/api/auth/me` | Get current user profile |
| `PUT`  | `/api/auth/me` | Update profile |

### Disease Detection

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/analyze` | Upload image â†’ leaf check + disease prediction |
| `POST` | `/api/predict` | Legacy file-upload prediction |
| `GET`  | `/api/model-status` | Model load status + training metadata |
| `GET`  | `/api/health` | Health check |

### Chat & Messaging

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/chat` | AI assistant message |
| `POST` | `/api/messages` | Send message to another user |
| `GET`  | `/api/messages/conversations` | List conversations |
| `GET`  | `/api/messages/<conv_id>` | Get messages in a conversation |

### Feedback & Retraining (Admin)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/feedback` | Submit a correction |
| `POST` | `/api/admin/retrain` | Trigger manual retraining |
| `GET`  | `/api/admin/retrain/status` | Pipeline status + model registry |
| `POST` | `/api/admin/retrain/rollback` | Roll back to previous model |

### Users & Detections

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/api/detections` | Detection history |
| `GET`  | `/api/detections/<id>` | Single detection |
| `DELETE` | `/api/detections/<id>` | Delete detection |
| `GET`  | `/api/users` | List all users (admin only) |
| `GET`  | `/api/users/stats` | User statistics (admin only) |

---

## ML Feedback Retraining Pipeline

The system includes a complete production-grade retraining pipeline that runs automatically or on demand.

### How it works

1. **Ingestion** â€” Collects feedback from `feedback.json`, the database, and stored correction images.
2. **Validation** â€” Filters verified entries, removes duplicates, detects inconsistent labels, and validates classes.
3. **Preprocessing** â€” Merges original training data with feedback into a unified train/val split.
4. **Training** â€” Fine-tunes the champion model (incremental) or trains from scratch (full).
5. **Evaluation** â€” Compares challenger vs champion on accuracy, precision, recall, and F1-score.
6. **Deployment** â€” Promotes the new model only if it improves by at least the configured threshold. Keeps previous versions for rollback.

### Run manually (CLI)

```bash
cd backend

# Dry-run: train and evaluate, but do not deploy
python pipeline_runner.py --mode incremental --epochs 10 --dry-run

# Full retraining from scratch
python pipeline_runner.py --mode full --epochs 30

# Roll back to previous champion
python pipeline_runner.py --rollback
```

### Run via admin API

```bash
# Trigger retraining (requires admin JWT)
curl -X POST http://localhost:5000/api/admin/retrain \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"mode": "incremental", "epochs": 10}'

# Roll back
curl -X POST http://localhost:5000/api/admin/retrain/rollback \
  -H "Authorization: Bearer <admin_token>"
```

### Scheduling

Set `RETRAIN_SCHEDULE=weekly` (or `monthly`) to enable automatic background retraining via APScheduler. Use `off` to disable.

---

## Docker

Build and run locally with Docker:

```bash
# Build image
docker build -t AgroSightAI-api .

# Run container
docker run -p 5000:5000 \
  -e SECRET_KEY=your-secret \
  -e JWT_SECRET_KEY=your-jwt-secret \
  -e CORS_ORIGINS=http://localhost:8080 \
  AgroSightAI-api
```

Or use Docker Compose (includes the backend):

```bash
docker-compose up
```

---

## Deploy to Render

1. Push this repository to GitHub.
2. In Render Dashboard, click **New â†’ Blueprint**.
3. Connect your GitHub repository.
4. Render will read `render.yaml` and automatically provision:
   - A Python web service (`AgroSightAI-api`)
   - A managed PostgreSQL database (`AgroSightAI-db`)
5. Environment variables (`SECRET_KEY`, `JWT_SECRET_KEY`, `DATABASE_URL`) are generated/injected automatically.
6. On first deploy, tables are auto-created. Your data will persist across restarts.

**Important:** The free PostgreSQL tier expires after 90 days of inactivity. Upgrade to a paid plan for production use.

---

## Dataset

The model is trained on the **PlantVillage** dataset subset covering:

- **Corn (Maize):** Cercospora leaf spot, Common rust, Northern Leaf Blight, Healthy
- **Potato:** Early blight, Late blight, Healthy
- **Tomato:** Bacterial spot, Early blight, Late blight, Leaf Mold, Septoria leaf spot, Spider mites, Target Spot, Yellow Leaf Curl Virus, Mosaic virus, Healthy

Place raw images in `dataset/color/<class_name>/` and run `backend/utils/dataset_prep.py` to generate train/val/test splits.

---

## Troubleshooting

### Flask app won't start
- Ensure you are using **Python 3.11**. TensorFlow 2.16 is not compatible with 3.12+.
- Activate the correct virtual environment (`venv311`, not `venv` which may contain Python 3.14).
- Verify `saved_models/best_model_finetuned.keras` or `best_model.keras` exists.

### CORS errors in browser
- Set `CORS_ORIGINS` to your frontend origin (e.g., `http://localhost:8080`).
- Do not use `*` in production with credentials enabled.

### Model predictions are mocked
- The app falls back to mock predictions if the Keras model fails to load. Check logs for the specific load error.
- Ensure `saved_models/class_indices.json` exists alongside the model file.

### Chat server not connecting
- The Node.js chat server must be running on port 5001.
- Update `SOCKET_URL` in your environment if deploying to a non-localhost domain.

### Pipeline aborts with "insufficient feedback"
- The pipeline requires at least `MIN_FEEDBACK_COUNT` (default 5) verified feedback entries.
- Submit corrections via the frontend or `POST /api/feedback`.

---

## License

MIT
