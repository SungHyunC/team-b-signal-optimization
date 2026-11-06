# Production image of the live SUMO twin (deployed on Render through render.yaml).
# Runtime dependencies only; the test tools (pytest, httpx) are the "dev" extra and stay out.
# The base image is pinned by digest so Render and CI build the same thing. To move it:
#   docker buildx imagetools inspect python:3.11-slim   (copy the top-level Digest)
FROM python:3.11-slim@sha256:65bd3d9f1d7fa268dd1909973ba7eb4bdf41f6dcf2cfbe76ba9528b170f3fd79
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
# Shared libraries the pip-provided SUMO binaries load on a slim image (libxrender1: PR #10),
# and tini as PID 1 so SUMO processes orphaned by a killed search get reaped.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 libxrender1 tini \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements.lock ./
RUN python -m pip install --no-cache-dir -r requirements.txt -c requirements.lock
COPY . .
# Non-root runtime user. The code stays root-owned (read-only for the app); only results/ and
# the generated SUMO network are writable.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin app \
 && mkdir -p results teamb/network/generated \
 && chown -R app:app results teamb/network/generated
USER app
# Build the network and run a 120 s SUMO smoke simulation now, as the runtime user: a missing
# shared library or an unwritable directory fails `docker build` instead of the first visitor,
# and the prebuilt network makes cold starts faster.
RUN python -m teamb doctor
ENV PORT=10000
EXPOSE 10000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('PORT', '10000'), timeout=4)"
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["sh", "-c", "exec python -m uvicorn teamb.twin.server:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1"]
