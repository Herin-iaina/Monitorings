FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Installer dépendances système nécessaires pour certaines wheels/nettoyage
RUN apt-get update \
     && apt-get install -y --no-install-recommends \
         build-essential \
         libssl-dev \
         libffi-dev \
         openssh-client \
         iputils-ping \
         net-tools \
     && rm -rf /var/lib/apt/lists/*

# Installer dépendances Python
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copier le projet
COPY . /app

# Créer un utilisateur non-root
RUN useradd -m appuser || true
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Lancer le runner qui démarre l'API et le scheduler
CMD ["python", "runner.py"]
