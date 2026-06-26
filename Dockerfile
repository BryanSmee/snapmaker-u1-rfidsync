FROM python:3.14-slim

# Don't write .pyc files; flush stdout/stderr so container logs are live.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first so they cache across code changes.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application code and the config snippets uploaded to the printer on boot.
COPY rfidsync ./rfidsync
COPY cfg ./cfg

# All runtime configuration comes from environment variables (see README).
ENTRYPOINT ["python", "-m", "rfidsync"]
