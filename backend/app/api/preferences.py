"""偏好管理路由。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.postgres import get_db
from app.schemas.rag import PreferenceOut, PreferenceUpsert
from app.services import preference_service as ps

router = APIRouter(prefix="/api/preferences", tags=["preferences"])


@router.get("", response_model=list[PreferenceOut])
def list_prefs(db: Session = Depends(get_db)):
    return ps.list_preferences(db)


@router.put("", response_model=PreferenceOut)
def upsert_pref(body: PreferenceUpsert, db: Session = Depends(get_db)):
    return PreferenceOut(**ps.upsert_preference(db, body.key, body.value, body.description))


@router.delete("/{key}")
def delete_pref(key: str, db: Session = Depends(get_db)):
    if not ps.delete_preference(db, key):
        raise HTTPException(status_code=404, detail="偏好不存在")
    return {"ok": True, "key": key}
