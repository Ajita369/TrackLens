# TrackLens — Store Intelligence System

TrackLens is an end-to-end computer vision and metrics api pipeline that turns raw store CCTV feeds into actionable physical store intelligence. Starting from anonymized video footage, the system detects, tracks, and re-identifies visitors, handles staff exclusions, correlates transaction records, and produces structured events to power a metrics api and live dashboard.

## Quick Start (5 Steps)

Follow these steps to set up and run the TrackLens API locally:

```bash
# 1. Clone the repository
git clone https://github.com/Ajita369/TrackLens.git
cd Tracklens

# 2. Place dataset files in the correct directories under data/:
# For Original Store (ST1008):
# - Raw videos: data/clips/CAM 1.mp4, CAM 2.mp4, etc.
# - Layout file: data/Brigade Road - Store layoutc5f5d56.xlsx
# - Transactions: data/Brigade_Bangalore_10_April_26 (1)bc6219c.csv
#
# For New Store (ST1076):
# - Raw videos: data/Store 1-20260602T101818Z-3-001ec38db8/Store 1/...
# - Events file: data/sample_eventsbe42122.jsonl
# - Transactions: data/POS - sample transactionsb1e826f.csv

# 3. Build and start the API service
docker compose up --build -d

# 4. Ingest events (automatically detects and seeds ST1076 if present, else ST1008)
python scripts/seed_events.py

# 5. Query store metrics using curl
# For ST1008 (Original Store):
curl "http://localhost:8000/stores/ST1008/metrics?date=2026-04-10"
# For ST1076 (New Store):
curl "http://localhost:8000/stores/ST1076/metrics?date=2026-03-08"
```

## Running Detection Pipeline
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

## Live Dashboard & Simulator

TrackLens includes a live-updating web-based dashboard that visualizes traffic metrics, purchase funnels, zone heatmaps, and active anomaly alerts in real-time.

### Running the Dashboard:
1. Ensure the API service is running:
   ```bash
   docker compose up --build -d
   ```
2. In a separate terminal, start the event playback simulation tool (replaying generated events from the pipeline output at a 10x speed multiplier):
   ```bash
    # For the Original Store (ST1008):
    python dashboard/simulate.py --store ST1008 --speed 10
    
    # For the New Store (ST1076):
    python dashboard/simulate.py --store ST1076 --speed 10
   ```
3. Open your browser and navigate to:
   ```
   http://localhost:8000/dashboard/
   ```

## Architecture Documentation

For a detailed exploration of system components, pipeline stages, re-identification algorithms, and AI-assisted decisions, refer to these file in docs folder:
* **System Design Blueprint**: [DESIGN.md](file:///C:/projects/TrackLens/docs/DESIGN.md)
* **Technical Design Decisions**: [CHOICES.md](file:///C:/projects/TrackLens/docs/CHOICES.md)

## Running Tests

TrackLens has a comprehensive test suite covering edge cases (such as zero-purchase stores, empty/all-staff events), schema validations, and metrics calculations. 

To run the tests with code coverage analysis inside the Docker container:
```bash
docker compose exec api pytest tests/ -v --cov=app --cov-report=term-missing --cov-fail-under=70
```

To run the tests locally:
```bash
python -m pytest tests/ -v --cov=app --cov-report=term-missing
```

## Dataset Structure

> [!NOTE]
> The `data/clips` directory is explicitly excluded from the Git repository (via `.gitignore`) to avoid committing large binary CCTV video files. To run or test the system locally, please place the store intelligence dataset files directly into the directory structure below.

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

## Dataset Support (Brigade Road & Store 1 / Store 2)

The system automatically and dynamically resolves and normalizes both the original Brigade Road dataset and the new Store 1 / Store 2 datasets:
- **POS Transactions**: Supports the original `Brigade_Bangalore_10_April_26 (1)bc6219c.csv` file as well as the new `POS - sample transactionsb1e826f.csv` filename.
- **Event Ingestion & Replay**: Seamlessly processes both the standard schema (`sample_events.jsonl`) and the alternative tracking/demographics schema format (`sample_eventsbe42122.jsonl`). On-the-fly normalization resolves store codes (e.g. `store_1076` -> `ST1076`), matches local camera track IDs to entry/exit tokens using demographic attributes, generates synthetic `ZONE_DWELL` events from `ZONE_EXIT` events, and auto-injects correlated POS records for queue completions.

