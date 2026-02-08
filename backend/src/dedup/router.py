"""Duplicate Detection API routes."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/dedup", tags=["dedup"])
