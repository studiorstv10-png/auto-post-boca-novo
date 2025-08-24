FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 10000
CMD ["gunicorn", "--workers", "1", "boca_app:app", "--timeout", "120"]
