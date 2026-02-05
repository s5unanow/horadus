# PostgreSQL 16 + TimescaleDB with pgvector installed.
#
# The upstream timescale image is Alpine-based and does not provide a
# PostgreSQL 16-specific pgvector package out of the box. Build pgvector
# against the bundled PostgreSQL 16 toolchain so `CREATE EXTENSION vector`
# works during init/migrations.

FROM timescale/timescaledb:latest-pg16

ARG PGVECTOR_TAG=v0.8.1

RUN set -eux; \
  apk add --no-cache --virtual .build-deps \
    build-base \
    clang19 \
    llvm19 \
    git \
    ca-certificates; \
  git clone --depth 1 --branch "${PGVECTOR_TAG}" https://github.com/pgvector/pgvector.git /tmp/pgvector; \
  make -C /tmp/pgvector; \
  make -C /tmp/pgvector install; \
  rm -rf /tmp/pgvector; \
  apk del .build-deps
