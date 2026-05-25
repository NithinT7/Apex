from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.activity_routes import router as activity_router
from app.api.car_routes import router as car_router
from app.api.career_routes import router as career_router
from app.api.data_routes import router as data_router
from app.api.decision_routes import router as decision_router
from app.api.development_routes import router as development_router
from app.api.health_routes import router as health_router
from app.api.interview_routes import router as interview_router
from app.api.save_routes import router as save_router
from app.api.sponsor_routes import router as sponsor_router
from app.api.season_routes import router as season_router
from app.api.weekend_routes import router as weekend_router


app = FastAPI(title="F1 Career Simulator API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(career_router)
app.include_router(data_router)
app.include_router(save_router)
app.include_router(weekend_router)
app.include_router(decision_router)
app.include_router(activity_router)
app.include_router(development_router)
app.include_router(interview_router)
app.include_router(car_router)
app.include_router(season_router)
app.include_router(sponsor_router)
