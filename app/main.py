from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import time
import uuid
import sqlite3
import logging
import json
import re

from app.database import init_db
from app.logging_config import setup_logging
from app.ingestion import router as ingestion_router
from app.metrics import router as metrics_router
from app.health import router as health_router
from app.funnel import router as funnel_router
from app.heatmap import router as heatmap_router
from app.anomalies import router as anomalies_router

# Initialize structured logging at the start
setup_logging()
logger = logging.getLogger("tracklens_api")

app = FastAPI(title="TrackLens API", version="1.0.0")

# Enable CORS for all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Regular expression to extract store_id from path (e.g. /stores/ST1008/metrics)
STORE_ID_PATTERN = re.compile(r"/stores/([^/]+)")

# Request logging middleware
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    trace_id = str(uuid.uuid4())
    request.state.trace_id = trace_id
    
    start_time = time.perf_counter()
    
    method = request.method
    path = request.url.path
    
    # Extract store_id from path if present
    store_match = STORE_ID_PATTERN.search(path)
    store_id = store_match.group(1) if store_match else None
    
    # Capture event count for ingestion requests
    event_count = None
    if path == "/events/ingest" and method == "POST":
        try:
            body = await request.body()
            # Restore the request body receive channel so the endpoint can read it again
            async def receive():
                return {"type": "http.request", "body": body, "more_body": False}
            request._receive = receive
            
            payload = json.loads(body.decode("utf-8"))
            if isinstance(payload, dict) and "events" in payload:
                event_count = len(payload["events"])
        except Exception:
            event_count = 0
            
    # Process request
    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception as exc:
        # Exceptions will be caught by handlers, but if they leak out:
        status_code = 500
        raise exc
    finally:
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        
        # Log structured request telemetry using extra_fields
        log_fields = {
            "trace_id": trace_id,
            "method": method,
            "path": path,
            "store_id": store_id,
            "latency_ms": round(latency_ms, 2),
            "status_code": status_code
        }
        if event_count is not None:
            log_fields["event_count"] = event_count
            
        logger.info(
            f"Request processed: {method} {path} - Status {status_code}",
            extra={"extra_fields": log_fields}
        )
        
    return response

# Call database initialization on startup
@app.on_event("startup")
def startup_event():
    init_db()

# Include routers
app.include_router(ingestion_router)
app.include_router(metrics_router)
app.include_router(health_router)
app.include_router(funnel_router)
app.include_router(heatmap_router)
app.include_router(anomalies_router)

# Serve dashboard static files
app.mount("/dashboard", StaticFiles(directory="dashboard/static", html=True), name="dashboard")

# Database Unavailability Handler (503 Service Unavailable)
@app.exception_handler(sqlite3.OperationalError)
def db_operational_exception_handler(request: Request, exc: sqlite3.OperationalError):
    trace_id = getattr(request.state, "trace_id", "unknown")
    logger.error(
        f"Database operation failed: {exc}", 
        exc_info=True, 
        extra={"extra_fields": {"trace_id": trace_id, "error_type": "database_operational_error"}}
    )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        headers={"Retry-After": "5"},
        content={
            "error": "service_unavailable",
            "message": "Database temporarily unavailable. Please retry shortly.",
            "trace_id": trace_id,
            "retry_after_seconds": 5
        }
    )

# Global Exception Handler (500 Internal Server Error, zero raw stack traces to client)
@app.exception_handler(Exception)
def global_exception_handler(request: Request, exc: Exception):
    trace_id = getattr(request.state, "trace_id", "unknown")
    logger.error(
        f"Unhandled exception occurred: {exc}", 
        exc_info=True, 
        extra={"extra_fields": {"trace_id": trace_id, "error_type": "unhandled_system_exception"}}
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred. Please contact the administrator.",
            "trace_id": trace_id
        }
    )
