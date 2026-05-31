from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.database import init_db
from app.ingestion import router as ingestion_router
from app.metrics import router as metrics_router
from app.health import router as health_router
from app.funnel import router as funnel_router
from app.heatmap import router as heatmap_router
from app.anomalies import router as anomalies_router
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

# Call database initialization on startup (this will also seed POS data if empty)
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

# Global Exception Handler (Zero raw stack traces returned to client)
@app.exception_handler(Exception)
def global_exception_handler(request: Request, exc: Exception):
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
