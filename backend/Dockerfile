FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY app/ ./app/

# Set DB (fine for demo)
ENV DATABASE_URL=sqlite:///./recon.db

# Run FastAPI on Fly port
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8080"]