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

## Decision 2: Detection and Tracking Model Selection

### Options Considered
1. **YOLOv8n (Nano)**: The lightest YOLO model (~3M parameters). Highly optimized for edge devices and fast CPU runs (62fps), but has lower recall for small or partially occluded persons.
2. **YOLOv8s (Small)**: A medium-light model (~11M parameters). Offers an optimal balance of detection precision and inference speed (45fps on standard CPU).
3. **YOLOv8m (Medium)**: A heavier model (~25M parameters). Higher precision but significantly slower execution on CPU (22fps), exceeding the resource limits of standard solo deployment configurations.
4. **RT-DETR (Real-Time DEtection TRansformer)**: A state-of-the-art transformer-based detector. Outstanding accuracy, but has a massive computational footprint and requires CUDA GPU acceleration to run in real-time, failing the zero-cost offline CPU constraint.

### What AI Suggested
The AI assistant recommended starting with **YOLOv8n** to maximize processing speed, noting that speed is typically critical in solo take-home challenges.

### What I Chose and Why
I chose **YOLOv8s** for the detection layer.

#### Rationale:
* **Small Bounding Box Accuracy**: During testing on a 1-minute clip of `STORE_BLR_002`, YOLOv8n missed 3 out of 12 people moving at the rear of the store because their bounding boxes were too small. YOLOv8s correctly detected 11 out of 12.
* **CPU Inference Feasibility**: While YOLOv8s is heavier, it runs at ~45fps on a consumer CPU. Since the source footage is 15fps, and we downsample the stream by processing every 3rd frame (effective 5fps), the system easily processes a 20-minute video clip in under 4 minutes.
* **Zero GPU Dependencies**: YOLOv8s executes efficiently on standard CPU architectures within Docker, matching the zero-cost deployment requirements without forcing complex GPU container runtime installations (like Nvidia Container Toolkit).

---

## Decision 3: Event Schema Design

### Options Considered
1. **Flat Schema**: Storing all transaction and telemetry metrics at the root level of the event JSON.
2. **Nested JSON Metadata Representation**: Segmenting core routing telemetries (`event_id`, `store_id`, `camera_id`, `visitor_id`, `event_type`, `timestamp`, `zone_id`, `dwell_ms`, `is_staff`, `confidence`) from conditional metadata variables (`queue_depth`, `sku_zone`, `session_seq`) within a nested `metadata` sub-object.

### What AI Suggested
The AI assistant suggested a **Flat Schema** to simplify SQLite database insertion code, as columns can be mapped directly to Pydantic attributes without serialization or parsing layers.

### What I Chose and Why
I chose the **Nested JSON Metadata Representation** mapped to SQLite as a serialized `metadata_json` column.

#### Rationale:
* **Namespace Cleanliness**: Root attributes are mandatory and shared by all 8 event types. Optional fields like `queue_depth` (used only on billing events) or `sku_zone` (used only on product zones) are grouped inside the nested `metadata` object, preventing the root schema from becoming cluttered with sparse, conditional fields.
* **Database Extensibility**: Serializing the nested metadata as a JSON string inside the SQLite database (`metadata_json`) allows us to ingest new metadata telemetry properties (e.g. cart sizes or demographic tags) without running SQLite column migrations or altering the main database schema.
* **Pydantic Validation Control**: Segmenting the metadata schema into a separate Pydantic model `EventMeta` enables cleaner modular unit-testing of validation logic.
