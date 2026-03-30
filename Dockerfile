# Image officielle Playwright — contient Chromium + toutes les dépendances système
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

# Dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code source
COPY . .

# Port API
EXPOSE 8000

# Lancement
CMD ["python", "main.py"]
