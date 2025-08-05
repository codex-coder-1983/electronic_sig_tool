# Use an official Python image
FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libxext6 \
    libsm6 \
    libxrender1 \
    libpoppler-cpp-dev \
    build-essential \
    python3-dev \
    pkg-config \
    libmupdf-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Install Python dependencies
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Set environment variable for Flask
ENV PYTHONUNBUFFERED=1

# Start command
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:10000"]