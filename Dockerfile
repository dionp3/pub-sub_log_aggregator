FROM python:3.11-slim
WORKDIR /app

ENV PYTHONPATH=/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

RUN adduser --disabled-password --gecos '' appuser 

COPY src/ ./src/ 
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8080