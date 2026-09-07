FROM python:3.12-slim AS app
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py ask.py ./
COPY dashboard.py dashboard.html dashboard.js ./
COPY src ./src
COPY prompts ./prompts
COPY tests ./tests
ENTRYPOINT ["python"]
CMD ["main.py"]

FROM app AS daily
RUN apt-get update && apt-get install -y --no-install-recommends cron && rm -rf /var/lib/apt/lists/*
COPY deploy/daily.py /app/deploy/daily.py
CMD ["deploy/daily.py", "--schedule"]

FROM app AS default
