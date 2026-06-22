# Local Development README Design

## Objective

Replace the root `README.md` with a Chinese, command-oriented local development guide. The guide must let a developer start Jellyfish from a clean checkout and diagnose the most common startup failures without searching across component-specific documentation.

## Scope

The README will document the recommended hybrid development topology:

- MySQL, Redis, and RustFS run through `deploy/compose/docker-compose.infra.yml`.
- FastAPI Backend, Celery Worker, and Vite Frontend run as host processes for fast reload and direct logs.
- The full `deploy/compose/docker-compose.yml` stack remains an optional alternative.

The existing long product and feature overview will be replaced by a short project introduction. The README will not duplicate architecture, release notes, deployment procedures, or production hardening guidance.

## Document Structure

1. Project title and short description.
2. Recommended local topology and service/port table.
3. Prerequisites: Docker, `uv`, Node.js, and pnpm.
4. Environment setup:
   - Copy `deploy/compose/.env.local.example` to `.env.local`.
   - Copy `backend/.env.example` to `backend/.env`.
   - Align MySQL, Redis, RustFS, CORS, JWT, and initial administrator settings.
5. Start infrastructure with the explicit Compose file and environment file.
6. Check container health and logs.
7. Initialize or migrate the database:
   - Explain that SQLAlchemy `create_all()` creates missing tables but does not alter existing tables.
   - Explain the difference between a new database and an existing persistent volume.
   - Provide a non-interactive command that pipes the required scripts from the host into the MySQL client inside the container.
   - Identify `009-add-users-and-user-isolation.sql` as the migration required for databases missing `generation_tasks.user_id`.
8. Start the Backend with Uvicorn and verify `/health` and `/docs`.
9. Start the Celery Worker and identify the `ready` log marker.
10. Start the Frontend with pnpm and open port `7788`.
11. Provide the recommended startup order and a concise verification checklist.
12. Provide stop commands and an explicitly destructive volume-reset command.
13. Troubleshooting:
    - MySQL connection refused.
    - Missing `INITIAL_ADMIN_PASSWORD`.
    - Browser reports CORS while the API actually returns HTTP 500.
    - Missing database columns because a persistent database was not migrated.
    - Worker cannot connect to Redis.
14. Optional full-stack Compose startup.
15. OpenAPI client synchronization requirement after API changes.
16. License reference.

## Command and Safety Requirements

- Commands must assume execution from the repository root unless a section explicitly changes directory.
- Compose commands must always include both `--env-file deploy/compose/.env.local` and `-f deploy/compose/docker-compose.infra.yml`.
- Passwords must not be embedded directly in command examples. Container-side environment variables or an interactive password prompt must be used.
- Destructive commands such as `docker compose down -v` must be labeled as deleting local data.
- Each long-running process must be shown in a separate terminal section.
- Paths and service names must match the current repository: `front`, `backend`, `mysql`, `redis`, and `rustfs`.

## Validation

After editing the README:

- Verify every referenced file exists.
- Validate the resolved infrastructure Compose configuration with `docker compose ... config --quiet`.
- Confirm Backend and Frontend script names against `backend/pyproject.toml` and `front/package.json`.
- Scan the README for stale paths such as `frontend/` or an unspecified Compose `.env` file.
- Review the final diff to ensure the replacement is limited to `README.md` plus this approved design artifact.

## Completion Criteria

The work is complete when the root README contains a reproducible local startup flow for infrastructure, migrations, Backend, Worker, and Frontend; commands match the repository; safety warnings are explicit; and the documented validation commands pass.
