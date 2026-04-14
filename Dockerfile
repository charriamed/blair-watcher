FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render détecte le port 10000
EXPOSE 10000

CMD ["python", "blair_status_watcher.py"]
