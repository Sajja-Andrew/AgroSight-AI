# AgroSight AI — Production Deployment Guide

## Quick Start (Local Docker)

```bash
# 1. Copy environment file and configure secrets
cp .env.example .env
# Edit .env — change all passwords and secrets

# 2. Build and start all services
docker compose up --build -d

# 3. Run database migrations (first run only)
docker compose exec api flask db upgrade

# 4. Create admin user
docker compose exec api python -c "
from backend.database import create_admin, init_app
from backend.app import app
init_app(app)
with app.app_context():
    create_admin('admin', 'admin@agrosight.ai', 'ChangeMe123!')
"

# 5. Open the app
open http://localhost:8080
```

## Production Deployment

Deploy with the enterprise `docker-compose.prod.yml` overlay for resource limits, security hardening, centralized logging, and monitoring.

### Prerequisites

- Docker Engine 24.0+ with Compose v2
- 8 GB RAM minimum (16 GB recommended)
- 4 CPU cores minimum
- 50 GB disk space for backups and logs

### Required `.env` Variables

The following secrets and configuration values **must** be set before starting production services. The compose file uses bash-style variable validation (`:?`) and will fail fast if any are missing.

| Variable | Example | Purpose |
|----------|---------|---------|
| `SECRET_KEY` | `openssl rand -hex 32` | Flask session signing |
| `JWT_SECRET_KEY` | `openssl rand -hex 32` | JWT token signing |
| `POSTGRES_PASSWORD` | Strong password | PostgreSQL superuser |
| `MINIO_SECRET_KEY` | MinIO root password | Object storage root account |
| `DATABASE_URL` | `postgresql://...` | Full Postgres connection string |
| `CORS_ORIGINS` | `https://agrosight.ai` | Allowed frontend origin |

Generate secure keys:

```bash
openssl rand -hex 32 > .postgres_password
openssl rand -hex 32 > .secret_key
openssl rand -hex 32 > .jwt_secret_key
```

### Start Production Stack

```bash
# 1. Validate environment
docker compose -f docker-compose.yml -f docker-compose.prod.yml config > /dev/null

# 2. Build and start with production overrides
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d

# 3. Verify all services are healthy
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps

# 4. Run database migrations
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api flask db upgrade

# 5. Initialize MinIO buckets
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api python scripts/init-minio.py
```

### Scaling App Replicas

The production overlay supports Docker Swarm-style `deploy.replicas`. To run multiple app containers behind a load balancer:

```bash
# Requires Docker Swarm mode
docker swarm init
docker stack deploy -c docker-compose.yml -c docker-compose.prod.yml agrosight

# Scale to 3 replicas
 docker service scale agrosight_app=3
```

For single-host deployments, keep `APP_REPLICAS=1` (default).

### Security Hardening

`docker-compose.prod.yml` applies the following hardening to every service:

| Hardening | Applied To | Details |
|-----------|------------|---------|
| `read_only: true` | All | Root filesystem is read-only |
| `user:` | All | Runs as non-root dedicated user |
| `cap_drop: [ALL]` | All | Drops all Linux capabilities |
| `security_opt: [no-new-privileges:true]` | All | Prevents privilege escalation |
| `cap_add` | Selective | Only adds back `NET_BIND_SERVICE`, `CHOWN`, `SETGID`, `SETUID` where needed |
| `tmpfs` | All | Writable `/tmp` and `/dev/shm` are memory-backed, not disk |
| Network isolation | DB / Cache | `internal-net` has no external route; only `public-net` services (Nginx) are exposed |

**Why this matters:** If a container is compromised, the attacker cannot write malware to disk, escalate to root, or pivot to the host kernel. The read-only root filesystem combined with capability dropping is the Docker equivalent of running as an unprivileged user in a chroot jail.

### Resource Limits

Default limits per service (tunable via `.env`):

| Service | CPU Limit | Memory Limit | CPU Reserve | Memory Reserve |
|---------|-----------|--------------|-------------|----------------|
| App | 4.0 | 8 GB | 2.0 | 4 GB |
| PostgreSQL | 2.0 | 2 GB | 1.0 | 1 GB |
| MinIO | 2.0 | 2 GB | 0.5 | 512 MB |
| Redis | 1.0 | 512 MB | 0.25 | 256 MB |
| Prometheus | 1.0 | 1 GB | 0.5 | 512 MB |
| Loki | 1.0 | 1 GB | 0.25 | 256 MB |
| Grafana | 1.0 | 512 MB | 0.25 | 128 MB |

Override in `.env`:

```bash
APP_CPU_LIMIT=8.0
APP_MEM_LIMIT=16G
POSTGRES_MEM_LIMIT=4G
```

### TensorFlow / AI Memory Optimization

Production containers limit TensorFlow thread pools to prevent CPU starvation:

```bash
OMP_NUM_THREADS=4
MKL_NUM_THREADS=4
OPENBLAS_NUM_THREADS=4
TF_FORCE_GPU_ALLOW_GROWTH=true
```

On a server with 8+ cores, increase these to `8` for faster inference. On a 2-core VPS, reduce to `2`.

## Services Architecture

| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| App | `agrosight-app` | `8080` | Nginx + Flask + Node.js (unified) |
| PostgreSQL | `agrosight-postgres` | `5432` | Primary database |
| MinIO | `agrosight-minio` | `9000` / `9001` | Object storage (S3 API / Console) |
| Redis | `agrosight-redis` | `6379` | Cache / sessions |

## Environment Variables

See `.env.example` for all options. Critical secrets to change:

- `SECRET_KEY`
- `JWT_SECRET_KEY`
- `POSTGRES_PASSWORD`
- `MINIO_SECRET_KEY`

## Docker Compose Commands

```bash
# Start everything
docker compose up -d

# View logs
docker compose logs -f app

# Restart a service
docker compose restart app

# Scale Gunicorn workers (edit .env then restart)
docker compose up -d --no-deps app

# Stop everything
docker compose down

# Stop and remove volumes (⚠️ destroys data)
docker compose down -v

# Database shell
docker compose exec postgres psql -U agrosight -d agrosight

# MinIO console (dev only)
open http://localhost:9001
```

## Cloud Deployment

### Render

1. Create a **Web Service** from your GitHub repo.
2. Set **Environment** to `Docker`.
3. Add a **PostgreSQL** managed database.
4. Set environment variables in the Render dashboard.
5. The `render.yaml` file in this repo can be used with **Render Blueprints**.

### Railway

1. Connect your GitHub repo to Railway.
2. Railway auto-detects `docker-compose.yml`.
3. Add a PostgreSQL addon from the Railway dashboard.
4. Set `DATABASE_URL` to the Railway Postgres connection string.

### DigitalOcean / AWS EC2 / VPS

```bash
# On Ubuntu 22.04+ server
sudo apt update && sudo apt install -y docker.io docker-compose

git clone https://github.com/your-org/agrosight-ai.git
cd agrosight-ai
cp .env.example .env
# Edit .env with production values

docker compose up --build -d
```

### SSL with Let's Encrypt

Use the external Nginx service (uncomment in `docker-compose.yml`) with Certbot:

```bash
docker run -it --rm \
  -v "$(pwd)/docker/ssl:/etc/letsencrypt" \
  -v "$(pwd)/docker/nginx-external.conf:/etc/nginx/conf.d/default.conf" \
  certbot/certbot certonly --standalone -d yourdomain.com
```

## Monitoring Stack (Prometheus + Loki + Grafana)

The production compose includes a full observability stack. All metrics and logs are collected automatically — no manual instrumentation required.

### Accessing Dashboards

| Service | URL | Credentials | Notes |
|---------|-----|-------------|-------|
| Grafana | `http://localhost:3000` | `admin` / `.env` `GRAFANA_ADMIN_PASSWORD` | Centralized metrics + logs |
| Prometheus | `http://localhost:9090` | None (read-only UI) | Raw metrics query engine |
| Loki | `http://localhost:3100` | None (API only) | Log aggregation backend |

**Security note:** In production, bind these ports to `127.0.0.1` only (as configured in `docker-compose.prod.yml`). Access them via SSH tunnel or VPN:

```bash
# SSH tunnel from your laptop to the server
ssh -L 3000:localhost:3000 -L 9090:localhost:9090 user@agrosight-server
# Then open http://localhost:3000 on your laptop
```

### Pre-configured Dashboards

Grafana auto-provisions dashboards on startup from `docker/grafana-provisioning/dashboards/`:

1. **AgroSight AI Overview** — API request rate, latency p95/p99, error rate, active users
2. **Node Exporter** — CPU, memory, disk, network per host
3. **PostgreSQL** — Query throughput, slow queries, connection count, replication lag
4. **Redis** — Memory usage, hit rate, evictions, connected clients
5. **MinIO** — Bucket size, request rate, error rate

### Alerting Rules

Prometheus scraping + Grafana alerting is pre-wired. Key alerts:

| Alert | Threshold | Action |
|-------|-----------|--------|
| API High Error Rate | > 5% 5xx for 5 min | Page on-call |
| API Latency p95 | > 2s for 10 min | Scale app replicas |
| PostgreSQL Connections | > 80% max | Investigate connection leaks |
| Disk Usage | > 85% | Trigger backup cleanup |
| Memory Usage | > 90% | Restart app or scale up |
| MinIO Down | 0 healthy for 1 min | Check MinIO container |

Configure notification channels in Grafana UI: **Alerting → Contact points → Add Slack / PagerDuty / Email**.

### Log Aggregation with Loki

All containers stream JSON logs to Loki via the Docker logging driver. Query logs in Grafana:

```logql
# All API error logs
{container_name="agrosight-app"} |= "ERROR" | json

# Slow requests (> 1s)
{container_name="agrosight-app"} | json | response_time_ms > 1000

# PostgreSQL slow queries
{container_name="agrosight-postgres"} |= "duration:"

# Authentication failures
{container_name="agrosight-app"} |= "Unauthorized" or "login failed"
```

### Health Checks

- App container: `docker inspect --format='{{.State.Health.Status}}' agrosight-app`
- API: `curl http://localhost:8080/api/health`
- PostgreSQL: `docker compose exec postgres pg_isready`
- MinIO: `curl http://localhost:9000/minio/health/live`

## Backup Strategy

### Automated Daily Backups

The `scripts/backup.sh` script runs inside the app container via cron:

```bash
# Add to host crontab (runs at 2 AM UTC)
0 2 * * * cd /opt/agrosight-ai && docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T app /app/scripts/backup.sh
```

What gets backed up:

| Asset | Method | Retention |
|-------|--------|-----------|
| PostgreSQL | `pg_dump` custom format | 30 days (configurable via `BACKUP_RETENTION_DAYS`) |
| MinIO buckets | `mc mirror` | 30 days |
| Saved ML models | `tar.gz` | 30 days |
| Uploads | `tar.gz` | 30 days |
| Environment config | Sanitized `env` export | 30 days |

Backups are stored in `/backups` (mounted to `postgres-backups` volume by default). Move this to external storage (S3, NFS) for disaster recovery:

```bash
# Sync to AWS S3 after backup
aws s3 sync /var/lib/docker/volumes/agrosight_postgres-backups/_data/ s3://agrosight-backups/
```

### Restore from Backup

```bash
# 1. List available backups
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api ls -la /backups

# 2. Restore a specific backup
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T app /app/scripts/restore.sh /backups/agrosight_backup_20260511_020000.tar.gz

# 3. Verify database connectivity after restore
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api flask db current
```

### Health Monitoring & Alerting

The `scripts/monitor.sh` script checks all critical services every minute and sends Slack alerts on failure with a 10-minute cooldown to prevent spam.

```bash
# Add to host crontab
* * * * * cd /opt/agrosight-ai && docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T app /app/scripts/monitor.sh
```

Required environment variable:

```bash
SLACK_WEBHOOK=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

Checks performed:

- API health endpoint (`/api/health`)
- PostgreSQL connectivity (`pg_isready`)
- MinIO health (`/minio/health/live`)
- Redis connectivity (`redis-cli ping`)
- Disk usage (> 90% triggers critical alert)
- Memory usage (> 95% triggers critical alert)

Alerts auto-clear when the service recovers.

### PostgreSQL
```bash
# Automated daily backup via cron on host
docker compose exec -T postgres pg_dump -U agrosight agrosight > backup_$(date +%F).sql
```

### MinIO
```bash
# Mirror buckets to local backup
mc alias set agrosight http://localhost:9000 agrosight YOUR_SECRET
mc mirror agrosight/uploads ./backups/minio
```

### Model Files
```bash
# Compress and backup saved_models
tar czf models_backup_$(date +%F).tar.gz saved_models/
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `Connection refused` to Postgres | Wait 30s on first start; check `docker compose logs postgres` |
| TensorFlow model not loading | Ensure `saved_models/` is mounted as volume or copied into image |
| Socket.IO not connecting | Check Nginx WebSocket headers in `docker/nginx.conf` |
| MinIO upload fails | Verify bucket exists: `docker compose exec api python scripts/init-minio.py` |
| CORS errors | Set `CORS_ORIGINS` to your domain in `.env` |

## Kubernetes Migration

The `docker-compose.yml` structure is compatible with **Kompose**:

```bash
kompose convert -f docker-compose.yml
kubectl apply -f .
```

For production K8s, use Helm charts and separate the app into:
- `deployment-flask.yaml`
- `deployment-node.yaml`
- `deployment-nginx.yaml`
- `statefulset-postgres.yaml`
- `statefulset-minio.yaml`
