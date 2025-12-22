FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (including OpenGL for OpenCV)
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application code
COPY backend/ /app/backend/

# Copy scripts and ML modules (needed at runtime)
COPY scripts/ /app/scripts/
COPY ml/ /app/ml/

# Expose port
EXPOSE 5000

# Run the FastAPI server
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "5000"]
