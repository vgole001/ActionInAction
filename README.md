# ActionInAction


FROM python:3.11-slim

# Set environment variables

ENV PYTHONDONTWRITEBYTECODE=1 
    PYTHONUNBUFFERED=1

# Set work directory

WORKDIR /app

# Install system dependencies

RUN apt-get update && apt-get install -y 
    curl
    && apt-get clean
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code

COPY . .

# Expose port

EXPOSE 8000

# Health check

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

CMD [python -m uvicorn main:app --host 0.0.0.0.0 --port 8000]

# Workflow
Runs: On push to main/master or manual trigger.
Does:

Clones repo to GitHub’s Ubuntu runner.
Sets up Docker Buildx.
Logs into Docker Hub with DOCKER_USERNAME/DOCKER_PASSWORD secrets.
Builds Docker image from Dockerfile (not docker-compose.yml or main.py).
Pushes image to Docker Hub as <your-username>/fastapi-app:latest and <your-username>/fastapi-app:<commit-sha>.
Prints success message with pull/deploy instructions.

What It Uses

Dockerfile: Yes, it builds the image using the Dockerfile in your repo’s root (specified by context: .).
docker-compose.yml: No, it’s not used. The workflow only builds/pushes the image, not runs containers.
main.py: Indirectly, as it’s part of the app code included in the Dockerfile build. The workflow doesn’t directly use main.py.

Summary: Workflow uses Dockerfile to build the FastAPI app image and pushes it to Docker Hub. No docker-compose.yml or direct main.py usage.