FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY scripts ./scripts

RUN useradd --create-home --uid 10001 greyartifact
USER greyartifact

EXPOSE 5000
CMD ["python", "src/run.py"]
