FROM mcr.microsoft.com/playwright/python:v1.55.0-jammy

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Install your Python deps. Include playwright to match the base version.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy your code
COPY src /app/src

# Use the non-root Playwright user provided by the image
USER pwuser

ENTRYPOINT ["python", "/app/src/scraper.py"]