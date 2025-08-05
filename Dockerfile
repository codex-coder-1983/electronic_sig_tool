FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    poppler-utils \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Copy files
COPY . /app

# Install Python packages
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Expose the port
EXPOSE 10000

# Run the app
CMD ["python", "app.py"]