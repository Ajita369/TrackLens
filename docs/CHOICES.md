# Technical Choices

This document outlines the core technical design decisions made during the construction of the TrackLens Store Intelligence system, documenting the trade-offs, AI suggestions, and final chosen implementations.

---

## Decision 1: SQLite over PostgreSQL for Storage

### Options Considered
1. **PostgreSQL**: A fully featured, highly scalable, and concurrent relational database system.
2. **Redis**: An in-memory key-value store optimized for real-time counters and simple key lookup.
3. **SQLite**: A lightweight, disk-backed, zero-configuration relational database engine embedded directly in the application runtime.

### What AI Suggested
The AI assistant recommended a containerized PostgreSQL instance linked via Docker Compose networks, accessing the database through an Object-Relational Mapper (ORM) like SQLAlchemy or Tortoise ORM.

### What I Chose and Why
I decided to use **SQLite via Python's standard library `sqlite3` without an ORM**.

#### Rationale:
- **Zero-Cost & Zero-Configuration**: SQLite runs embedded inside the Python process. It requires no installation, no credentials, no port forwarding, and no background daemon process.
- **Scaffold Simplification**: Setting up a PostgreSQL service in `docker-compose.yml` adds significant bootstrap time: waiting for the DB to initialize, managing connection pools, handling database migrations, and configuring network parameters. In a solo take-home challenge with a tight time budget, these represent major failure vectors that do not add functionality to the core scoring goals.
- **WAL Concurrency**: By executing `PRAGMA journal_mode=WAL;` (Write-Ahead Logging), SQLite separates writers and readers. Multiple threads or asynchronous API calls can read the database file while a writer is appending events, preventing the database from locking under ordinary transaction volumes.
- **Sufficient Scale**: The challenge consists of 5 stores, 20-minute video clips, and around 1,000 generated events total. This volume is trivial for SQLite, which can easily index and query millions of rows within milliseconds.
- **SQL Control**: Writing raw SQL queries gives us complete control over performance and query planning without the black-box abstraction of an ORM, making debugging conversion rate calculations or queue depth lookups straightforward.

---

## Decision 2: Detection and Tracking Model Selection [TODO]

### Options Considered
- YOLOv8n (Nano)
- YOLOv8s (Small)
- MediaPipe Object Detector
- RT-DETR

### What AI Suggested
- *Marked as TODO. To be fully updated in Phase 5.*

### What I Chose and Why
- *Marked as TODO. To be fully updated in Phase 5.*

---

## Decision 3: Event Schema Design [TODO]

### Options Considered
- Flat Schema
- Nested JSON metadata representation

### What AI Suggested
- *Marked as TODO. To be fully updated in Phase 5.*

### What I Chose and Why
- *Marked as TODO. To be fully updated in Phase 5.*
