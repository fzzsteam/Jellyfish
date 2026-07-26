#!/usr/bin/env bash
# 本地一键启动/重启脚本。
#
# 用法：
#   ./dev.sh          启动全部服务；已在运行的会先探测并重启，Docker 基础设施除外
#   ./dev.sh stop     停止 Backend / Worker / Frontend（不动 Docker 基础设施）
#
# 行为约定：
#   - Docker 基础设施（MySQL/Redis/RustFS）：只执行 `up -d`，不重启已运行的容器
#     （`up -d` 本身幂等，已运行的容器不受影响，只会拉起尚未运行的容器）。
#   - 数据库迁移（backend/apply_migrations.py）：MySQL healthy 后、启动 Backend 前执行，
#     幂等可重复执行；失败会中止整个脚本，避免 Backend 跑在未迁移的旧 schema 上。
#   - Backend / Celery Worker / Frontend：每次都会探测端口或进程是否已在运行，
#     若在运行则先停止，再重新启动，保证代码变更总能生效。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$ROOT_DIR/logs"
PID_DIR="$ROOT_DIR/.pids"
mkdir -p "$LOG_DIR" "$PID_DIR"

BACKEND_PORT=8000
FRONTEND_PORT=7788

COMPOSE_ENV_FILE="$ROOT_DIR/deploy/compose/.env.local"
COMPOSE_FILE="$ROOT_DIR/deploy/compose/docker-compose.infra.yml"

BACKEND_PATTERN="uvicorn app\.main:app"
WORKER_PATTERN="celery -A app\.core\.celery_app:celery_app worker"
FRONTEND_PATTERN="front/node_modules/.*vite"

log() { echo "[dev.sh] $*"; }

# 停止匹配指定命令行模式的进程（先 TERM，超时后 KILL）。
stop_by_pattern() {
  local pattern="$1"
  local name="$2"
  if pgrep -f "$pattern" >/dev/null 2>&1; then
    log "探测到 ${name} 正在运行，正在停止..."
    pkill -f "$pattern" 2>/dev/null || true
    for _ in $(seq 1 10); do
      pgrep -f "$pattern" >/dev/null 2>&1 || break
      sleep 0.5
    done
    if pgrep -f "$pattern" >/dev/null 2>&1; then
      log "${name} 未在超时内退出，强制 kill -9"
      pkill -9 -f "$pattern" 2>/dev/null || true
    fi
  fi
}

# 兜底：按端口清理残留进程（防止进程名匹配不到但端口仍被占用的情况）。
stop_by_port() {
  local port="$1"
  local name="$2"
  local pids
  pids="$(lsof -ti tcp:"$port" 2>/dev/null || true)"
  if [ -n "$pids" ]; then
    log "端口 ${port}（${name}）仍被占用（PID: ${pids}），强制释放"
    kill -9 $pids 2>/dev/null || true
  fi
}

# 轮询等待 URL 返回 2xx/3xx，用于确认服务已就绪。
wait_for_http() {
  local url="$1"
  local name="$2"
  local tries="${3:-30}"
  for _ in $(seq 1 "$tries"); do
    if curl -sf --noproxy '*' -o /dev/null "$url"; then
      log "${name} 已就绪：${url}"
      return 0
    fi
    sleep 1
  done
  log "警告：${name} 在预期时间内未就绪，请检查日志：${LOG_DIR}/$(echo "$name" | tr '[:upper:]' '[:lower:]').log"
  return 1
}

check_prereq_files() {
  local missing=0
  if [ ! -f "$COMPOSE_ENV_FILE" ]; then
    log "缺少 ${COMPOSE_ENV_FILE}，请先执行： cp deploy/compose/.env.local.example deploy/compose/.env.local"
    missing=1
  fi
  if [ ! -f "$ROOT_DIR/backend/.env" ]; then
    log "缺少 backend/.env，请先执行： cp backend/.env.example backend/.env"
    missing=1
  fi
  if [ "$missing" -eq 1 ]; then
    exit 1
  fi
}

stop_all() {
  log "==> 停止 Frontend / Worker / Backend（Docker 基础设施不受影响）"
  stop_by_pattern "$FRONTEND_PATTERN" "Frontend"
  stop_by_port "$FRONTEND_PORT" "Frontend"
  stop_by_pattern "$WORKER_PATTERN" "Celery Worker"
  stop_by_pattern "$BACKEND_PATTERN" "Backend"
  stop_by_port "$BACKEND_PORT" "Backend"
  rm -f "$PID_DIR"/*.pid
  log "已停止。"
}

start_infra() {
  log "==> 检查 Docker 基础设施（MySQL / Redis / RustFS）"
  docker compose --env-file "$COMPOSE_ENV_FILE" -f "$COMPOSE_FILE" up -d

  log "等待 MySQL / Redis 变为 healthy..."
  for _ in $(seq 1 30); do
    mysql_status="$(docker inspect -f '{{.State.Health.Status}}' compose-mysql-1 2>/dev/null || echo unknown)"
    redis_status="$(docker inspect -f '{{.State.Health.Status}}' compose-redis-1 2>/dev/null || echo unknown)"
    if [ "$mysql_status" = "healthy" ] && [ "$redis_status" = "healthy" ]; then
      log "MySQL / Redis 均已 healthy"
      break
    fi
    sleep 1
  done
  if [ "${mysql_status:-}" != "healthy" ] || [ "${redis_status:-}" != "healthy" ]; then
    log "警告：MySQL(${mysql_status:-unknown}) / Redis(${redis_status:-unknown}) 未在预期时间内 healthy，请检查："
    log "  docker compose --env-file deploy/compose/.env.local -f deploy/compose/docker-compose.infra.yml logs mysql redis"
  fi
}

run_migrations() {
  log "==> 执行数据库迁移 (backend/apply_migrations.py)"
  if ! (cd "$ROOT_DIR/backend" && uv run python apply_migrations.py); then
    log "数据库迁移失败，已中止启动，请检查上方输出后重试"
    exit 1
  fi
}

start_backend() {
  log "==> 启动 Backend (uvicorn :${BACKEND_PORT})"
  stop_by_pattern "$BACKEND_PATTERN" "Backend"
  stop_by_port "$BACKEND_PORT" "Backend"
  (
    cd "$ROOT_DIR/backend"
    nohup uv run uvicorn app.main:app --reload --host 0.0.0.0 --port "$BACKEND_PORT" \
      >"$LOG_DIR/backend.log" 2>&1 &
    echo $! >"$PID_DIR/backend.pid"
  )
  log "Backend 已启动，PID $(cat "$PID_DIR/backend.pid")，日志：${LOG_DIR}/backend.log"
}

start_worker() {
  log "==> 启动 Celery Worker（含 Beat）"
  stop_by_pattern "$WORKER_PATTERN" "Celery Worker"
  (
    cd "$ROOT_DIR/backend"
    nohup uv run celery -A app.core.celery_app:celery_app worker --beat -l info \
      >"$LOG_DIR/worker.log" 2>&1 &
    echo $! >"$PID_DIR/worker.pid"
  )
  log "Celery Worker 已启动，PID $(cat "$PID_DIR/worker.pid")，日志：${LOG_DIR}/worker.log"
}

start_frontend() {
  log "==> 启动 Frontend (vite :${FRONTEND_PORT})"
  stop_by_pattern "$FRONTEND_PATTERN" "Frontend"
  stop_by_port "$FRONTEND_PORT" "Frontend"
  (
    cd "$ROOT_DIR/front"
    nohup pnpm dev >"$LOG_DIR/frontend.log" 2>&1 &
    echo $! >"$PID_DIR/frontend.pid"
  )
  log "Frontend 已启动，PID $(cat "$PID_DIR/frontend.pid")，日志：${LOG_DIR}/frontend.log"
}

start_all() {
  check_prereq_files
  start_infra
  run_migrations
  start_backend
  wait_for_http "http://127.0.0.1:${BACKEND_PORT}/health" "Backend" 30 || true
  start_worker
  start_frontend
  # vite 不带 --host 时只监听 localhost（本机可能解析为 IPv6 ::1），
  # 探测必须用 localhost 而非 127.0.0.1，否则会被拒绝连接。
  wait_for_http "http://localhost:${FRONTEND_PORT}" "Frontend" 30 || true

  echo
  log "==> 全部启动完成"
  log "  Frontend : http://localhost:${FRONTEND_PORT}"
  log "  Backend  : http://localhost:${BACKEND_PORT}  (docs: http://localhost:${BACKEND_PORT}/docs)"
  log "  日志目录 : ${LOG_DIR}"
  log "  停止命令 : ./dev.sh stop"
}

case "${1:-start}" in
  start|restart|"")
    start_all
    ;;
  stop)
    stop_all
    ;;
  *)
    echo "用法: $0 [start|stop]" >&2
    exit 1
    ;;
esac
