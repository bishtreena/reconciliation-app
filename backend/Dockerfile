FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY app/ ./app/

# Use PORT from Render
ENV PORT=10000

# Optional: fallback DB (can override in Render env)
ENV DATABASE_URL=sqlite:///./recon.db

# Run app
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port $PORT"]