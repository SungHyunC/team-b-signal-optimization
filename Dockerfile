FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /app/results
ENV PORT=10000
EXPOSE 10000
CMD ["sh", "-c", "exec python -m uvicorn teamb.twin.server:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1"]
