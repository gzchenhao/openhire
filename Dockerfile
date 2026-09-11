# OpenHire MCP server — container image (Docker MCP Registry / self-hosting).
# stdio by default (Docker MCP Toolkit); pass `--transport streamable-http --host 0.0.0.0`
# as CMD to expose an HTTP endpoint on :8000. First run auto-downloads the public job
# snapshot (jobs/companies only — never user data) into /data.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OPENHIRE_HOME=/data

WORKDIR /src
COPY pyproject.toml README.md LICENSE* ./
COPY src ./src
RUN pip install --no-cache-dir . && rm -rf /src

WORKDIR /data
VOLUME ["/data"]
EXPOSE 8000

ENTRYPOINT ["ohp", "serve"]
CMD []
