FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CHUMA_HOST=0.0.0.0 \
    CHUMA_DATA_DIR=/data
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir 'psycopg[binary]>=3.2,<4'
EXPOSE 8097
CMD ["python", "run.py"]
