"""Versioned API router."""

from fastapi import APIRouter

from app.api.v1 import aliases, answers, documents, jobs, makers, otel, status

router = APIRouter()
router.include_router(status.router)
router.include_router(documents.router)
router.include_router(makers.router)
router.include_router(makers.model_router)
router.include_router(jobs.router)
router.include_router(answers.router)
router.include_router(aliases.router)
router.include_router(otel.router)
