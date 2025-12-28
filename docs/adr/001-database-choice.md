# ADR-001: PostgreSQL as Primary Database

**Status**: Accepted  
**Date**: 2025-01-XX  
**Deciders**: Architecture review

## Context

We need a database that can handle:
- Relational data (events, trends, evidence)
- Vector similarity search (embeddings)
- Time-series queries (trend history)
- High-volume writes (news ingestion)

Options considered: PostgreSQL, MongoDB, separate specialized databases.

## Decision

Use **PostgreSQL** with extensions:
- **pgvector** for embedding similarity search
- **TimescaleDB** for time-series data

One database for all storage needs.

## Consequences

### Positive
- Single database to operate, backup, monitor
- ACID transactions across all data
- SQL joins for complex queries
- No data synchronization issues
- Mature ecosystem, well-documented

### Negative
- pgvector less performant than dedicated vector DBs at massive scale
- TimescaleDB adds operational complexity vs plain Postgres

### Neutral
- Need to learn pgvector and TimescaleDB specifics

## Alternatives Considered

### Alternative 1: MongoDB
- Pros: Flexible schema, easy to start
- Cons: Poor for relational queries, no native vector search, no time-series
- Why rejected: Our data is highly relational (events → evidence → trends)

### Alternative 2: PostgreSQL + Pinecone + InfluxDB
- Pros: Best-in-class for each use case
- Cons: Three databases to operate, sync issues, higher cost
- Why rejected: Complexity not justified at our scale

### Alternative 3: PostgreSQL + Elasticsearch
- Pros: Better full-text search
- Cons: Data duplication, sync complexity
- Why rejected: PostgreSQL full-text search sufficient for our needs

## References

- [pgvector GitHub](https://github.com/pgvector/pgvector)
- [TimescaleDB Documentation](https://docs.timescale.com/)
