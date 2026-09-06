FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends docker.io ca-certificates && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir fastapi uvicorn
COPY firefox_gateway.py /app/firefox_gateway.py
WORKDIR /app
CMD ["uvicorn","firefox_gateway:app","--host","0.0.0.0","--port","8080"]
