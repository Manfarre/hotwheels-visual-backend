from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.health import router as health_router
from routes.ebay_auth import router as ebay_auth_router
from routes.ebay_tools import router as ebay_tools_router
from routes.match import router as match_router

app = FastAPI(title="Hot Wheels Visual Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(ebay_auth_router)
app.include_router(ebay_tools_router)
app.include_router(match_router)
