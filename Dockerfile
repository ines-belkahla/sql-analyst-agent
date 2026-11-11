# Shared development image for the three-person SQL Analyst project.
# Keep application code mounted from the host so teammates can edit in VS Code.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/root/.cache/huggingface \
    TOKENIZERS_PARALLELISM=false

WORKDIR /workspace

# git is required by some DVC workflows; libgomp1 is used by ML dependencies.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml ./
COPY data_engineering ./data_engineering
COPY evaluation ./evaluation
COPY agent ./agent

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

# Source is bind-mounted by Compose; this command keeps the dev container available.
CMD ["sleep", "infinity"]
