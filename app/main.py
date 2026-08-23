from fastapi import FastAPI

from app.api.routes_health import router as health_router

app = FastAPI(title="AI-Powered Indian Stock Swing Trading System")

app.include_router(health_router)
