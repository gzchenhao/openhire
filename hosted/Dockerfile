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
RUN pip install --no-cache-dir "openhire==0.8.14"

COPY --chown=user:user entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

USER user
WORKDIR /data
EXPOSE 7860

CMD ["/app/entrypoint.sh"]
