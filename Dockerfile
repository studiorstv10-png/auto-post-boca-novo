FROM python:3.11-slim

# ffmpeg para render de vídeo
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# copie suas fontes, logo e áudio para a imagem
COPY . .

# serviço worker (sem servidor web)
CMD ["python", "boca_app.py"]
