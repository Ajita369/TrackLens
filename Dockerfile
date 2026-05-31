FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application directories
COPY app/ app/
COPY dashboard/ dashboard/
RUN mkdir -p pipeline

# Set environment variables
ENV PORT=8000
ENV DATABASE_PATH=/app/data/tracklens.db

# Expose port
EXPOSE 8000

# Start FastAPI server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
