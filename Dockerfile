FROM python:3.12-slim

WORKDIR /app

# Install git and uv
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*
RUN pip install uv

# Copy requirements first for caching
COPY requirements.txt .
RUN uv pip install --system -r requirements.txt

# Copy source code
COPY . .

CMD ["python", "main.py"]
