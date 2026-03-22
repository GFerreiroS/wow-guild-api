FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev libpq-dev git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--reload", "--reload-include", ".env", "--host", "0.0.0.0"]
