from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status

from app.models.save_game import CreateSaveRequest, SaveGame, SaveSummary
from app.save.save_manager import SaveManager


router = APIRouter(prefix="/saves", tags=["saves"])
manager = SaveManager()


@router.post("", response_model=SaveGame, status_code=status.HTTP_201_CREATED)
def create_save(payload: CreateSaveRequest | None = None) -> SaveGame:
    return manager.create(payload)


@router.get("", response_model=list[SaveSummary])
def list_saves() -> list[SaveSummary]:
    return manager.list()


@router.get("/{save_id}", response_model=SaveGame)
def get_save(save_id: str) -> SaveGame:
    save = manager.get(save_id)
    if save is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Save not found")

    return save


@router.delete("/{save_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_save(save_id: str) -> Response:
    deleted = manager.delete(save_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Save not found")

    return Response(status_code=status.HTTP_204_NO_CONTENT)
