FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ITRADING_PARAMS_PROFILE=live

WORKDIR /app

COPY deploy/aws/requirements.aws.txt /tmp/requirements.aws.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /tmp/requirements.aws.txt

COPY . /app

CMD ["python", "-m", "itrading.scripts.run_forex_live"]
