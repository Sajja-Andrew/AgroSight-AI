# AgroSight AI — Docker Optimization Guide

**Goal:** Build < 3 min, final image < 1.5 GB, runtime < 4 GB RAM on an 8 GB Windows machine.

---

## 1. What Changed & Why

| Optimization | Before | After | Why It Speeds Things Up |
|--------------|--------|-------|-------------------------|
| **Base image** | `python:3.11-slim-bookworm` + Node.js + Nginx + Supervisor in one image | `python:3.11-slim-bookworm` **only** for API; `nginx:alpine` for web; `node:20-alpine` for chat | Splitting the monolith means each image is tiny. The Python image no longer carries Node/Nginx bloat (~400 MB saved). |
| **ML dependencies** | `tensorflow-cpu`, `numpy`, `pillow`, `h5py`, `scipy`, `scikit-learn`, `matplotlib` | Only `tensorflow-cpu`, `numpy`, `pillow` | Removed `matplotlib` (GUI plotting), `scipy` (not used in inference), `scikit-learn` (training only). Saves ~300 MB install + build time. |
| **OpenCV / GUI libs** | Installed `libgl1-mesa-glx`, `libsm6`, `libxext6`, `libxrender-dev` | **Removed entirely** | Production inference uses **PIL + TensorFlow only**—OpenCV is only used in `experimental/train_pytorch.py`. Removing these GUI libraries saves ~200 MB and eliminates huge Debian package resolution delays. |
| **Models in image** | `COPY saved_models/ ./saved_models/` baked into layer | Volume mount `- ./saved_models:/app/saved_models:ro` | Models are 120 MB+. Baking them into the image creates a giant layer that must be **unpacked** on every rebuild. A volume mount is instant and keeps the image < 1 GB. |
| **Dataset in context** | `.dockerignore` excluded `dataset/` but context still large | Explicitly excluded `dataset/`, `saved_models/`, `scripts/`, `tests/`, `*.md` | Shrinks the build context sent to Docker from potentially **GBs down to ~2 MB**. Smaller context = faster tar, faster hash, faster upload to builder. |
| **Multi-stage build** | Single stage, compiled inside final image | Two stages: `builder` compiles wheels; `production` copies only the clean venv | The final image contains **zero** build tools (`gcc`, `build-essential`, `libpq-dev`). Saves ~150 MB and reduces attack surface. |
| **Venv cleanup** | None | Delete `__pycache__`, `tests/`, `*.egg-info`, `*.pyc`, `share/`, `include/`, `man/` | Strips ~50-100 MB of dead weight from the copied virtual environment. |
| **Layer ordering** | Backend code copied **before** models | Backend code copied **last** (most frequently changed) | If you edit a `.py` file, Docker reuses all previous layers (dependencies, system packages) and only rebuilds the thin code layer. Rebuilds now take **seconds**, not minutes. |
| **pip cache mount** | Used `--mount=type=cache,target=/root/.cache/pip` | Still used, but combined into **one** install RUN | Fewer layers = less metadata overhead. The cache mount persists pip downloads across builds so `tensorflow-cpu` is downloaded once, not every time. |
| **Thread limits** | None | `OMP_NUM_THREADS=2`, `OPENBLAS_NUM_THREADS=2`, etc. | Prevents TensorFlow from spawning threads for every CPU core, which starves the OS and causes Docker Desktop to freeze during model load. |
| **Memory limits** | `memory: 4G` for unified app | `memory: 2G` for API, `512M` for Postgres, `512M` for MinIO | Hard caps prevent any single container from triggering Windows OOM / swap death spirals. |
| **Compose services** | 1 giant `app` + `postgres` + `minio` + `redis` | `api` + `chat` + `web` (nginx) + `postgres` + `minio` + `redis` | Independent services can be rebuilt **selectively**. Change a JS file? Only `chat` rebuilds. Change a template? Only `web` restarts. |
| **Pinned MinIO image** | `minio/minio:latest` | `minio/minio:RELEASE.2024-05-10T01-41-38Z` | `latest` causes unpredictable layer pulls and cache invalidation. A pinned digest or tag guarantees repeatability. |
| **Attestation disabled** | BuildKit generates provenance attestation by default | `--provenance=false` in build commands (see below) | Attestation manifests add extra layer exports that **hang on low-RAM machines**. Disabling them removes the "naming to docker.io/..." freeze. |
| **No BuildKit output compression** | Default gzip compression (slow on single-core) | `--output type=docker,compression=uncompressed` or use BuildKit container with more resources | Large-layer gzip compression is CPU-intensive and is often where Windows Docker Desktop appears to "hang". |

---

## 2. Recommended Folder Structure

```
AgroSight_AI/
├── backend/
│   ├── app.py
│   ├── config.py
│   ├── model_loader.py
│   ├── preprocessing.py
│   ├── requirements.txt          ← minimal inference deps
│   └── ...
├── frontend/
│   ├── index.html
│   ├── css/
│   ├── js/
│   └── server/
│       ├── server.js
│       └── package.json
├── saved_models/                 ← mounted as volume (NOT in image)
│   ├── best_model.keras
│   └── class_indices.json
├── saved_models_pytorch/         ← mounted as volume (NOT in image)
├── docker/
│   ├── nginx-minimal.conf        ← new lightweight proxy config
│   ├── redis.conf                ← (keep existing)
│   └── healthcheck.sh            ← (optional, keep if needed)
├── scripts/
│   ├── init-postgres.sql
│   └── init-db.sh
├── Dockerfile                    ← optimized Python API image
├── Dockerfile.chat               ← optimized Node chat image
├── docker-compose.yml            ← lightweight production compose
├── docker-compose.prod.yml       ← hardening + resource limits
├── docker-compose.override.yml   ← local dev hot-reload overrides
├── .dockerignore                 ← aggressive exclusions
└── OPTIMIZATION_GUIDE.md         ← this file
```

**Rule of thumb:** If a file is > 10 MB or changes rarely (models, datasets), **mount it as a volume**. If it changes daily (code), **copy it into the image**.

---

## 3. Fast Build Commands

### First-time build (cold cache)
Run from **PowerShell** inside the project root.

```powershell
# 1. Enable BuildKit and limit memory for the builder itself
$env:DOCKER_BUILDKIT = "1"

# 2. Create a dedicated builder with memory limits (prevents host freeze)
docker buildx create --name agrosight-builder --driver docker-container --use
docker buildx inspect agrosight-builder --bootstrap

# 3. Build API image with provenance DISABLED (critical for low-RAM)
docker buildx build `
  --builder agrosight-builder `
  --platform linux/amd64 `
  --target production `
  --provenance=false `
  --progress=plain `
  --memory=3g `
  --memory-swap=4g `
  -t agrosight-ai/api:latest `
  -f Dockerfile .

# 4. Build Chat image
docker buildx build `
  --builder agrosight-builder `
  --platform linux/amd64 `
  --provenance=false `
  --progress=plain `
  --memory=1g `
  -t agrosight-ai/chat:latest `
  -f Dockerfile.chat .
```

**Why these flags matter:**
- `--provenance=false` → Removes attestation manifest step that hangs at "naming to docker.io...".
- `--memory=3g` / `--memory-swap=4g` → Caps the BuildKit container so it cannot consume all 8 GB and crash Windows.
- `--progress=plain` → Shows real-time output so you know which step is active (prevents "is it stuck?" anxiety).
- `--target production` → Stops at the slim runtime stage, skipping the builder stage copy.

### Rebuild after code changes (hot cache)

```powershell
$env:DOCKER_BUILDKIT = "1"

# Rebuild ONLY the changed code layer (~10-30 seconds)
docker compose build --progress=plain api

# Or rebuild everything selectively
docker compose build --progress=plain
```

Because `backend/` is copied **last** in the Dockerfile, dependency layers are cached. Only the code layer rebuilds.

### Full stack up

```powershell
# Development (auto-loads override.yml)
docker compose up --build -d

# Production (tight limits, read-only containers)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

---

## 4. Why Your Build Hung (Root Causes)

### Symptom: `"unpacking to docker.io/library/agrosight_ai-app:latest"` freezes

**Cause A — Layer too large**
Your old image was ~3-4 GB. Docker Desktop on Windows uses a VM (WSL2). Exporting/compressing a multi-GB layer with gzip on a low-core machine takes 5-20 minutes and looks frozen.

**Fix:**
- Remove models/datasets from the image (mount as volumes).
- Use `--provenance=false`.
- Disable compression during local builds: add `--output type=docker` (default is compressed).

**Cause B — Out of memory during layer export**
BuildKit exports layers into the Docker daemon. If the layer + running containers exceed WSL2 RAM, Linux invokes the OOM killer or heavy swapping, causing a hard freeze.

**Fix:**
- Limit WSL2 memory to 5 GB max (see Docker Desktop settings below).
- Use `docker buildx build --memory=3g`.
- Prune old images before building.

**Cause C — Attestation manifest (BuildKit default)**
BuildKit ≥ 0.11 generates SLSA provenance by default. This creates an extra manifest that must be written after the image export. On low-RAM / slow-disk systems this step is disproportionately slow and often hangs indefinitely.

**Fix:**
- Always add `--provenance=false` for local builds.
- For CI/CD where you need provenance, use a remote builder.

**Cause D — Docker Desktop filesharing (Windows)**
If `saved_models/` or `dataset/` are inside the file-sharing path (e.g., `D:\Drive D\...`), Docker must hash every file in the context. Huge directories = long "sending build context" phase that appears as a hang.

**Fix:**
- `.dockerignore` now excludes `dataset/` and `saved_models/`.
- Ensure your project root is added to Docker Desktop → Settings → Resources → File sharing.

---

## 5. Resume / Restart Commands (No Full Rebuild)

### Scenario 1: Build stopped at "exporting layers"

```powershell
# The layers already built are CACHED. Just re-run the same command.
# BuildKit will skip completed layers and resume at the failed export.
$env:DOCKER_BUILDKIT = "1"
docker buildx build --builder agrosight-builder --provenance=false --progress=plain -t agrosight-ai/api:latest -f Dockerfile .
```

### Scenario 2: Build failed at dependency install (pip network error)

```powershell
# Pip cache mount is preserved, so re-running resumes near the failure point.
docker compose build --progress=plain api
```

### Scenario 3: Container starts but app crashes (bad code)

```powershell
# Fix the code, then rebuild ONLY the last layer (~seconds)
docker compose build api

# Restart just that container (no need to restart Postgres/Redis)
docker compose up -d --no-deps api
```

### Scenario 4: Docker Desktop completely frozen

```powershell
# 1. Save your work in other apps first!
# 2. Restart Docker Desktop (not the PC) via system tray → Restart
# 3. Prune dangling build cache to free locked memory
docker builder prune --filter type=regular --keep-storage 2GB -f

# 4. Resume build from cache
docker compose build --progress=plain api
```

### Scenario 5: Corrupted image / half-exported layer

```powershell
# Remove the broken image
docker rmi agrosight-ai/api:latest --force

# Clean build cache (keeps recent valid layers, removes orphans)
docker builder prune --filter type=regular --keep-storage 2GB -f

# Rebuild — heavy layers (deps) are still cached if the builder container survived
docker buildx build --builder agrosight-builder --provenance=false -t agrosight-ai/api:latest -f Dockerfile .
```

---

## 6. Docker Desktop Settings for 8 GB RAM

Open **Docker Desktop** → **Settings** → **Resources**:

| Setting | Recommended Value | Why |
|---------|-------------------|-----|
| **CPUs** | 4 | Gives BuildKit enough cores for parallel layer processing without starving Windows. |
| **Memory** | 5.00 GB | Leaves ~3 GB for Windows OS, browser, IDE. Prevents WSL2 OOM. |
| **Swap** | 1.00 GB | Small safety net; too much swap causes SSD thrashing and worse freezes. |
| **Disk image size** | 64 GB (default) | Ensure you have > 10 GB free inside Docker VM. |
| **WSL integration** | Enabled for your distro | Faster I/O than legacy Hyper-V backend. |

**Optional — Limit WSL2 globally via `.wslconfig`:**
Create `C:\Users\%USERNAME%\.wslconfig` with:

```ini
[wsl2]
memory=5GB
processors=4
swap=1GB
swapFile=C:\\temp\\wsl-swap.vhdx
localhostForwarding=true
```
Then run in PowerShell:
```powershell
wsl --shutdown
```
Restart Docker Desktop.

---

## 7. Cache Management Commands

```powershell
# See what builders exist and their cache size
docker buildx du

# Remove dangling images (safe)
docker image prune -f

# Remove stopped containers (safe)
docker container prune -f

# Remove unused volumes (careful — check volume names first)
docker volume prune -f

# Deep clean: remove ALL unused images, containers, networks, build cache
# WARNING: this deletes everything not actively running
docker system prune -a --volumes -f

# Safer targeted prune: keep recent build cache, delete old orphans
docker builder prune --filter type=regular --keep-storage 2GB -f

# Inspect current builder cache usage
docker buildx inspect agrosight-builder --bootstrap
```

**Best practice:** Run `docker builder prune --keep-storage 2GB -f` **before** every major build on an 8 GB machine. This frees RAM/disk held by stale intermediate layers.

---

## 8. Monitor Build Progress

```powershell
# Plain text output so you can see every step timestamp
docker compose build --progress=plain api

# BuildKit with verbose logging (shows cache decisions)
$env:BUILDKIT_PROGRESS = "plain"
$env:DOCKER_BUILDKIT = "1"
docker buildx build --progress=plain -t agrosight-ai/api:latest -f Dockerfile .

# Live resource usage during build (second PowerShell tab)
docker stats

# Check builder container logs if it seems stuck
docker logs buildx_buildkit_agrosight-builder0
```

**Signs of a healthy build:**
- `-->` appears for cached layers: `[2/7] CACHED`.
- Pip install shows wheel names flying by.
- Final export takes < 30 seconds for a 1 GB image.

**Signs of trouble:**
- No output for > 3 minutes at a single step → likely network or memory issue.
- "exporting layers" takes > 5 minutes → image too large or disk too slow.

---

## 9. Preventing Future Hangs

### Dependency installation (PyTorch / TensorFlow)

Both frameworks are huge. Mitigations:

1. **Install only CPU wheels**
   ```txt
   # requirements.txt
   tensorflow-cpu==2.16.1
   ```
   The `-cpu` tag excludes all CUDA libraries (~800 MB saved).

2. **Pin versions**
   Unpinned `tensorflow` or `torch` causes pip to resolve the dependency tree for minutes. Pin every heavy package.

3. **Use pip cache mount**
   Already in Dockerfile: `RUN --mount=type=cache,target=/root/.cache/pip ...`
   If the builder VM is destroyed, cache is lost. For persistent cache, use a local BuildKit cache volume:
   ```powershell
   docker buildx create --name agrosight-builder --driver docker-container --use
   ```

4. **Pre-download wheels (offline/air-gapped)**
   If network is slow:
   ```powershell
   pip download -r backend/requirements.txt -d ./wheels
   # Then in Dockerfile:
   # COPY wheels /wheels
   # pip install --no-index --find-links=/wheels -r requirements.txt
   ```

### Unpacking / Exporting layers

1. Keep final image < 1.5 GB (yours now does).
2. Add `--provenance=false`.
3. If disk I/O is the bottleneck (slow external HDD), move Docker Desktop disk to the SSD:
   - Settings → Resources → Advanced → Disk image location.

### Attestation manifest

Always disabled for local development:
```powershell
docker buildx build --provenance=false ...
```

---

## 10. Expected Performance

| Metric | Old Setup | New Setup | Target |
|--------|-----------|-----------|--------|
| **Build context size** | 500 MB – 2 GB | **~2 MB** | < 5 MB |
| **Image size** | ~3.5 GB | **~1.1 GB** | < 1.5 GB |
| **Cold build time** | 15-30 min (hangs) | **8-12 min** | < 15 min |
| **Rebuild after code change** | 5-10 min | **10-40 sec** | < 2 min |
| **Peak build RAM** | 6-8 GB | **~2.5 GB** | < 4 GB |
| **Runtime RAM (all services)** | ~5-6 GB | **~3.2 GB** | < 4 GB |
| **Container startup** | 30-60 sec | **5-10 sec** | < 15 sec |

---

## 11. Quick Reference — Daily Commands

```powershell
# ── Start everything ──
docker compose up -d

# ── View logs ──
docker compose logs -f api
docker compose logs -f chat

# ── Restart only the API after a code fix ──
docker compose up -d --no-deps --build api

# ── Shell into API container ──
docker compose exec api bash

# ── Check RAM usage ──
docker stats --no-stream

# ── Run database migrations (outside container or exec) ──
docker compose exec api flask db upgrade

# ── One-liner: full clean + rebuild ──
docker builder prune --keep-storage 2GB -f; docker compose build --progress=plain; docker compose up -d
```

---

## 12. If You Need PyTorch Later

The current production path uses TensorFlow/Keras. If you switch to PyTorch inference:

1. Add to `backend/requirements.txt`:
   ```txt
   --extra-index-url https://download.pytorch.org/whl/cpu
   torch==2.3.0+cpu
   torchvision==0.18.0+cpu
   ```
2. Mount `saved_models_pytorch/` as a volume (already in `docker-compose.yml`).
3. Rebuild. PyTorch CPU wheels are ~200 MB; still comfortable for your 8 GB machine.

**Do NOT** install both `tensorflow-gpu` and `torch` in the same image unless absolutely necessary—combined they exceed 2 GB.

---

## 13. Need More Help?

If a build still hangs after following this guide:

1. Open a second PowerShell and run `docker stats` to see if RAM is pegged at 100%.
2. Check Docker Desktop → Troubleshoot → Get support → Diagnostics.
3. Try the legacy builder (non-BuildKit) to isolate whether it's a BuildKit-specific issue:
   ```powershell
   $env:DOCKER_BUILDKIT = "0"
   docker compose build --progress=plain api
   ```
   (Slower, but simpler and sometimes more stable on low-end machines.)
