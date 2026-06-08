import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.api.routes_feed import router as feed_router
from app.api.routes_company_profile import router as company_profile_router

import app.models  # noqa: F401 — ensure all models registered

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logging.getLogger(__name__).info("Database initialized")
    yield


app = FastAPI(
    title="OfferGraph Agent Runtime",
    description="面试情报系统 - Agent Runtime API",
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

app.include_router(feed_router)
app.include_router(company_profile_router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "offergraph-agent-runtime"}
