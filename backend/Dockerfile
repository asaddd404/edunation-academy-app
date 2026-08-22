FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Runs as an unprivileged user: a remote-code bug in the PDF parser or in
# ffmpeg then lands as `app`, not as root inside the container -- which is
# the same uid as root on the host for anything bind-mounted.
#
# `uploads` is created and chowned here because the production compose mounts
# a named volume over it; Docker seeds a fresh volume from the image, so the
# directory has to exist with the right owner *before* the mount, or the
# non-root process cannot write into it.
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/uploads \
    && chown -R app:app /app
USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
