# Usa uma imagem oficial do Python como base
FROM python:3.11-slim

# Define o diretório de trabalho dentro do container
WORKDIR /app

# Atualiza os pacotes e instala o FFmpeg (essencial para vídeo)
RUN apt-get update && apt-get install -y ffmpeg --no-install-recommends && rm -rf /var/lib/apt/lists/*

# Copia o arquivo de dependências do Python
COPY requirements.txt .

# Instala as dependências do Python
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo o resto do seu projeto para dentro do container
COPY . .

# Expõe a porta que a aplicação vai usar
EXPOSE 10000

CMD ["gunicorn", "--workers", "1", "boca_app:app", "--timeout", "120"]
