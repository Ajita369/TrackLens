# TrackLens — System Design

## Architecture Overview

TrackLens is an end-to-end store analytics and intelligence system designed to unlock operational visibility in brick-and-mortar retail stores. Physical stores have historically been analytical blind spots compared to online channels; TrackLens bridges this gap by converting raw CCTV security video streams into structured behavioral data streams that drive a real-time analytics API and a visual dashboard.

The system is organized into a decoupled, stage-by-stage pipeline:

```
+-----------------------------------------------------------+
|                      Detection Layer                      |
|  - Frame extraction from 5 store camera feeds             |
|  - Person bounding-box detection (YOLOv8s)                |
|  - Spatial mapping (Store Layout Zone Polygons)           |
+-----------------------------------------------------------+
                              |
                              v
+-----------------------------------------------------------+
|                       Tracking Layer                      |
|  - Frame-to-frame movement tracking (ByteTrack)           |
|  - Cross-camera identity re-identification (Re-ID)        |
|  - Employee filtering (torso colors & behavior patterns)  |
+-----------------------------------------------------------+
                              |
                              v
+-----------------------------------------------------------+
|                   Event Emission Layer                    |
|  - State machines generating ENTRY, EXIT, ZONE_ENTER,     |
|    ZONE_EXIT, ZONE_DWELL, queue events, and REENTRY       |
|  - Time-correlation with POS transaction logs             |
+-----------------------------------------------------------+
                              | (JSON over HTTP)
                              v
+-----------------------------------------------------------+
|                     FastAPI API Server                    |
|  - Ingestion: Validate & write to SQLite (insert or ignore) |
|  - Query APIs: metrics, heatmaps, funnels, anomalies       |
+-----------------------------------------------------------+
                              |
                              v
+-----------------------------------------------------------+
|                       Live Dashboard                      |
|  - Web UI polling metrics to update store health,         |
|    conversion rates, queue lines, and traffic heatmaps     |
+-----------------------------------------------------------+
```

### Detection & Tracking (Offline Pipeline)
The pipeline is designed to run asynchronously or offline relative to the API server. In the detection layer, raw MP4 clips are decoded at a configurable frame rate (typically downsampled to 5-10 frames per second to reduce compute overhead). Bounding boxes of class "person" are detected on each frame using a YOLOv8s model. The tracking layer correlates these detections across consecutive frames to assign localized tracking IDs using ByteTrack. For store-wide consistency, appearance-based Re-ID vectors are extracted using an OSNet model on the torso crops, enabling matching across cameras (e.g. from Entry to Floor or Billing Counter) and detecting customer re-entry.

### Event Emission & Ingestion
Whenever state boundaries are crossed—such as entering a spatial zone polygon or remaining in a zone for longer than 30 seconds—the emitter generates structured JSON events. These events are validated by Pydantic schemas and ingested into the REST API via the `/events/ingest` endpoint. The API server stores events in a SQLite database utilizing Write-Ahead Logging (WAL) and indexes to support highly concurrent read and write operations.

### Analytics & Anomaly Engine
The query layer aggregates these database records on the fly to compute performance metrics. The metrics engine calculates total unique visitor counts, average dwell time per store zone, active queue depth, queue abandonment rates, and checkout conversion rates. The anomaly detection system runs rules against rolling historical averages to flag issues such as queue build-ups (critical), conversion drops (warning), and dead zones (info).

---

## AI-Assisted Decisions

This section documents where AI tools shaped the architectural design and implementation strategies for the TrackLens system.

### Decision 1: Database Storage Model
- **AI Recommendation**: The AI assistant initially suggested using a PostgreSQL container coupled with SQLAlchemy to support database storage and relational operations.
- **AI Rationale**: Relational databases like PostgreSQL are industry-standard for structured data, and SQLAlchemy provides a Pythonic interface with migrations (Alembic).
- **My Choice & Override**: I overrode the recommendation to use raw SQLite with standard library `sqlite3` and SQL queries.
- **My Rationale**: TrackLens is designed for a single-candidate coding challenge with strict constraints around zero-cost stacks and single-command deployment reliability. Introducing PostgreSQL requires a secondary Docker container, network setup, volume permissions, health checks, and database migration configurations—introducing multiple points of failure. SQLite handles the dataset volume (under 10,000 events) in microseconds, supports WAL mode for simultaneous reads and writes, requires no extra services, and stores data in a single file inside the mounted data volume.

### Decision 2: Event Ingestion Validation Pattern [TODO]
- *Marked as TODO. To be fully updated in Phase 5.*

### Decision 3: Cross-Camera Re-ID Strategy [TODO]
- *Marked as TODO. To be fully updated in Phase 5.*
