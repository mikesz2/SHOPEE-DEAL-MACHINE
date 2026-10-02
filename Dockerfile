FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONUTF8=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /app/data /app/logs /app/backups && useradd -r -u 10001 -g users sdm && chown -R sdm:users /app
USER sdm
EXPOSE 8787
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8787","--proxy-headers","--forwarded-allow-ips=*"]
