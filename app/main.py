from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.database import init_db
from app.ingestion import router as ingestion_router
from app.metrics import router as metrics_router
from app.health import router as health_router
import traceback
import sys

app = FastAPI(title="TrackLens API", version="1.0.0")

# Enable CORS for all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Call database initialization on startup
@app.on_event("startup")
def startup_event():
    init_db()

# Include routers
app.include_router(ingestion_router)
app.include_router(metrics_router)
app.include_router(health_router)

# Stub routes for funnel, heatmap, and anomalies
@app.get("/stores/{store_id}/funnel", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def get_store_funnel(store_id: str):
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={"status": "not_implemented", "message": "Funnel analytics are not implemented in Phase 1"}
    )

@app.get("/stores/{store_id}/heatmap", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def get_store_heatmap(store_id: str):
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={"status": "not_implemented", "message": "Heatmap analytics are not implemented in Phase 1"}
    )

@app.get("/stores/{store_id}/anomalies", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def get_store_anomalies(store_id: str):
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={"status": "not_implemented", "message": "Anomaly detection is not implemented in Phase 1"}
    )

# Global Exception Handler (Zero raw stack traces returned to client)
@app.exception_handler(Exception)
def global_exception_handler(request: Request, exc: Exception):
    # Print the traceback locally to stderr for development logs
    print(f"Unhandled exception occurred: {exc}", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred. Please contact the administrator.",
            "details": str(exc) if app.debug else None
        }
    )
