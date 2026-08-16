FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md ./
COPY code ./code
RUN pip install --no-cache-dir .
EXPOSE 8000
CMD ["uvicorn", "outreach_agent.main:app", "--host", "0.0.0.0", "--port", "8000"]
