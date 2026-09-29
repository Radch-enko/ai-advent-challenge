FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY profiles.json ./profiles.json
RUN pip install --no-cache-dir '.[observability]'

ENV COPIA_DATA_ROOT=/data
EXPOSE 8000
CMD ["uvicorn", "copia.service:app", "--host", "0.0.0.0", "--port", "8000"]
