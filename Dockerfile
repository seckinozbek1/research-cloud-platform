FROM python:3.12-slim

RUN apt-get update \
    && apt-get install --only-upgrade -y \
       openssl \
       libssl3t64 \
       openssl-provider-legacy \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.api.txt .
RUN pip install --no-cache-dir -r requirements.api.txt

COPY src/api.py ./src/api.py
COPY serving/education_attendance ./serving/education_attendance

EXPOSE 8000

CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
