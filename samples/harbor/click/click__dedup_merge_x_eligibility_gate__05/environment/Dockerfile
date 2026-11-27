FROM python:3.12.15-slim-bookworm@sha256:6a0e06f5ba0b373d051aabd3fffb9b873f27f9a2a3a14bcbe37dee6f0e3bbc70

RUN apt-get update \
 && apt-get install -y --no-install-recommends git less \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir pytest==9.0.2 iniconfig==2.3.0 packaging==26.0 pluggy==1.6.0 pygments==2.20.0 flit_core==3.12.0

# Only the base commit is fetched, so later upstream history is not in the image.
WORKDIR /app
RUN git init -q . \
 && git fetch -q --depth 1 https://github.com/pallets/click.git cf19179e8e2fd54c601378cec9e0d21bb12b6fb1 \
 && git -c advice.detachedHead=false checkout -q FETCH_HEAD \
 && rm -f .git/FETCH_HEAD

RUN pip install --no-cache-dir --no-deps --no-build-isolation -e .

ENV PYTHONDONTWRITEBYTECODE=1 LANG=C.UTF-8
