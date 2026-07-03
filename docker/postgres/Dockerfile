# PostgreSQL 16 + TimescaleDB with pgvector installed.
#
# The upstream timescale image is Alpine-based and does not provide a
# PostgreSQL 16-specific pgvector package out of the box. Build pgvector
# against the bundled PostgreSQL 16 toolchain so `CREATE EXTENSION vector`
# works during init/migrations.

FROM timescale/timescaledb:latest-pg16

ARG PGVECTOR_TAG=v0.8.1

RUN set -eux; \
  pg_configure="$(pg_config --configure)"; \
  # Match the LLVM toolchain major compiled into this PostgreSQL image. The
  # Timescale multi-arch tag can require different clang majors per platform.
  clang_major="$(printf '%s\n' "${pg_configure}" | sed -n "s/.*CLANG=[^ ]*clang-\([0-9][0-9]*\).*/\1/p")"; \
  if [ -z "${clang_major}" ]; then \
    clang_major="$(printf '%s\n' "${pg_configure}" | sed -n "s/.*LLVM_CONFIG=[^ ]*llvm\([0-9][0-9]*\)[^ ]*.*/\1/p")"; \
  fi; \
  test -n "${clang_major}"; \
  apk add --no-cache --virtual .build-deps \
    build-base \
    "clang${clang_major}" \
    "llvm${clang_major}" \
    git \
    ca-certificates; \
  git clone --depth 1 --branch "${PGVECTOR_TAG}" https://github.com/pgvector/pgvector.git /tmp/pgvector; \
  make -C /tmp/pgvector; \
  make -C /tmp/pgvector install; \
  rm -rf /tmp/pgvector; \
  apk del .build-deps
