# TrackLens — Store Intelligence System

TrackLens is an end-to-end computer vision and metrics api pipeline that turns raw store CCTV feeds into actionable physical store intelligence. Starting from anonymized video footage, the system detects, tracks, and re-identifies visitors, handles staff exclusions, correlates transaction records, and produces structured events to power a metrics api and live dashboard.

## Quick Start (5 Steps)

Follow these steps to set up and run the TrackLens API locally:

```bash
# 1. Clone the repository
git clone https://github.com/apexretail/tracklens.git
cd tracklens

# 2. Place dataset files in the correct directories:
# - Raw videos: data/clips/CAM 1.mp4, CAM 2.mp4, etc.
# - Layout file: data/Brigade Road - Store layoutc5f5d56.xlsx
# - Transactions: data/Brigade_Bangalore_10_April_26 (1)bc6219c.csv

# 3. Build and start the API service
docker compose up --build -d

# 4. Ingest mock/sample events to populate the SQLite database
python scripts/seed_events.py

# 5. Query store metrics using curl
curl "http://localhost:8000/stores/ST1008/metrics?date=2026-04-10"
```

## Running Detection Pipeline
*(Implementation detail of Phase 2)*
To run the offline computer vision detection pipeline, execute the run script:
```bash
./pipeline/run.sh
```
This generates event records under `data/output/` which can then be ingested to the API.

## API Endpoints

The API is fully documented at `/docs` (OpenAPI) once running, and exposes the following endpoints:

| Method | Endpoint | Description |
|:---|:---|:---|
| `POST` | `/events/ingest` | Ingests batches of up to 500 visitor tracking events. Idempotent. |
| `GET` | `/stores/{id}/metrics` | Returns store performance metrics (unique visitors, conversion, dwell times, queue depth). |
| `GET` | `/stores/{id}/funnel` | Returns conversion funnel progression: Entry &rarr; Zone Visit &rarr; Queue &rarr; Purchase. |
| `GET` | `/stores/{id}/heatmap` | Returns visit frequencies and normalized scores per layout zone. |
| `GET` | `/stores/{id}/anomalies` | Returns active operational anomalies (queue spikes, conversion drops, dead zones). |
| `GET` | `/health` | Returns service status and store feed staleness alerts. |

## Dataset Structure

Place your local resources in the following tree structure:
```
tracklens/
└── data/
    ├── clips/
    │   ├── CAM 1.mp4
    │   ├── CAM 2.mp4
    │   └── ...
    ├── Brigade Road - Store layoutc5f5d56.xlsx
    └── Brigade_Bangalore_10_April_26 (1)bc6219c.csv
```
The database will be automatically created as a single file inside the `data/` folder at `data/tracklens.db`.
