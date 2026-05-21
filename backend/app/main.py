from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.data_routes import router as data_router
from app.api.health_routes import router as health_router


app = FastAPI(title="F1 Career Simulator API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(data_router)
