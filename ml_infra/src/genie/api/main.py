"""FastAPI application entrypoint for Genie ML Infrastructure."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from genie.api.v1.discovery import router as discovery_router
from genie.api.v1.pharmacies import router as pharmacies_router
from genie.api.v1.products import router as products_router
from genie.api.v1.verify import router as verify_router
from genie.common.config import settings
from genie.common.exceptions import QualityGateError


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize connection pools, models, and warm caches
    yield
    # Cleanup


app = FastAPI(
    title="GENIE AI Verification API",
    description="The core machine learning and multi-signal verification layer powering Genium.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(QualityGateError)
async def quality_gate_exception_handler(request: Request, exc: QualityGateError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error_code": exc.code,
            "message": str(exc),
            "details": exc.details,
        },
    )


@app.get("/health", tags=["System"])
async def health_check():
    return {
        "status": "healthy",
        "service": "genie-ml-infra",
        "env": settings.ENV,
    }


app.include_router(verify_router, prefix="/v1")
app.include_router(products_router, prefix="/v1")
app.include_router(pharmacies_router, prefix="/v1")
app.include_router(discovery_router, prefix="/v1")
