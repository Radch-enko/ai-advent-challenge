FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY server.py ./
RUN pip install --no-cache-dir .
ENV MCP_HOST=0.0.0.0 MCP_PORT=8002
EXPOSE 8002
CMD ["copia-journal-mcp", "--transport", "streamable-http"]
