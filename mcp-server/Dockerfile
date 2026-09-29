FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY server.py ./
RUN pip install --no-cache-dir .
ENV MCP_HOST=0.0.0.0 MCP_PORT=8001
EXPOSE 8001
CMD ["copia-finances-mcp", "--transport", "streamable-http"]
