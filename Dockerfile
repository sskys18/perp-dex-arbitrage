FROM python:3.12-slim

WORKDIR /app

# Install git (needed for git-based dependencies) and uv
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*
RUN pip install uv

# Copy requirements first for caching
COPY requirements.txt .

# Use GitHub token for private repos
ARG GH_TOKEN
RUN git config --global url."https://${GH_TOKEN}@github.com/".insteadOf "https://github.com/"
RUN uv pip install --system -r requirements.txt
RUN git config --global --unset url."https://${GH_TOKEN}@github.com/".insteadOf

# Copy source code
COPY . .

CMD ["python", "main.py"]
