FROM python:3.14-alpine

RUN apk add --no-cache gcc musl-dev libffi-dev postgresql-dev git

WORKDIR /app

COPY requirements.txt ./

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--reload", "--reload-include", ".env", "--host", "0.0.0.0"]
