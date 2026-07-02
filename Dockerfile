FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY examples ./examples
COPY scripts ./scripts
RUN pip install --no-cache-dir -e .

EXPOSE 8000
CMD ["uvicorn", "support_agent_lab.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

