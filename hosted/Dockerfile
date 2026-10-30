# OpenHire hosted endpoint — the image a Hugging Face Space (Docker SDK) builds.
#
# This is the SAME server a user runs locally with `uvx openhire serve`, started in hosted
# mode (OPENHIRE_HOSTED=1): streamable-http on the port the Space exposes, a landing page
# and /healthz, a per-IP rate limit, and a worker that stages the new weekly snapshot and
# restarts to activate it. It exists for clients that can only reach a URL (ChatGPT
# connectors); the local install stays the recommended path, because there nothing of a
# search leaves the user's machine. It installs the RELEASED package from PyPI; the version
# below is pinned to pyproject.toml by tests/test_release.py.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OPENHIRE_HOME=/data \
    OPENHIRE_HOSTED=1 \
    PORT=7860

RUN useradd -m -u 1000 user && mkdir -p /data && chown user:user /data
# PyPI's CDN edges lag a release by minutes; a build started right after one fails with
# "no matching distribution" (seven failed Render builds on 2026-10-21). Retry for up to
# 15 minutes, then prove the pinned version is what got installed.
RUN for i in $(seq 1 30); do \
      pip install --no-cache-dir "openhire==0.8.34" && break; \
      echo "openhire==0.8.34 is not on this PyPI edge yet (attempt $i); retrying in 30 s"; sleep 30; \
    done \
 && ohp version | grep -q "0.8.34"
# The trust store the server verifies GitHub (the snapshot) and employer sites against.
# Render's 2026-10-23 advisory: eight eMudhra intermediate certificates were compromised
# (disclosed 2026-10-19); certifi 2026.10.19 and 2026.10.23 followed. httpx reads certifi,
# so it is upgraded after the pinned install; the system store is refreshed for anything
# else. This layer sits below the version line, so every release rebuilds it fresh.
RUN pip install --no-cache-dir --upgrade certifi \
 && apt-get update && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && python -c "import certifi; print('certifi', certifi.__version__)"

COPY --chown=user:user entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

USER user
WORKDIR /data
EXPOSE 7860

CMD ["/app/entrypoint.sh"]
