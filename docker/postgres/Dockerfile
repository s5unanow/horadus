# PostgreSQL 16 + TimescaleDB with pgvector installed.
#
# The upstream timescale image includes TimescaleDB, but pgvector availability
# varies by base image. Installing the package here ensures `CREATE EXTENSION vector`
# works reliably during init/migrations.

FROM timescale/timescaledb:latest-pg16

RUN apt-get update \
  && apt-get install -y --no-install-recommends postgresql-16-pgvector \
  && rm -rf /var/lib/apt/lists/*
