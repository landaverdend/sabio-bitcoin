# Frontend build -- output only, node itself never ships in the final image.
FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Backend runtime -- pinned to the same Python this project develops against
# (see .python-version), not just "3.12" floating.
FROM python:3.12.11-slim
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY agents/ ./agents/
COPY db/ ./db/
COPY jobs/ ./jobs/
COPY scripts/ ./scripts/
COPY --from=frontend /app/frontend/dist ./frontend/dist

EXPOSE 8080
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
