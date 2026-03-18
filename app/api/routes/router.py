from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import agent, clean, dataset_preview, datasets, explore, model, projects, prompts, report, visualize


api_router = APIRouter()
api_router.include_router(projects.router)
api_router.include_router(datasets.router)
api_router.include_router(prompts.router)
api_router.include_router(dataset_preview.router)
api_router.include_router(agent.router)
api_router.include_router(clean.router)
api_router.include_router(explore.router)
api_router.include_router(visualize.router)
api_router.include_router(model.router)
api_router.include_router(report.router)

