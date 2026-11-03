"""偏好服务: 用户偏好 / 记忆的增删改查 (Agent 对话时注入)。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import Preference
from app.logging_config import get_logger

log = get_logger("pref", "OPS")


def list_preferences(db: Session) -> list[dict]:
    rows = db.query(Preference).all()
    return [
        {"key": p.key, "value": p.value, "description": p.description,
         "updated_at": p.updated_at.isoformat() if p.updated_at else None}
        for p in rows
    ]


def upsert_preference(db: Session, key: str, value: str, description: str = "") -> dict:
    p = db.query(Preference).filter(Preference.key == key).first()
    if p:
        p.value = value
        if description:
            p.description = description
    else:
        p = Preference(key=key, value=value, description=description)
        db.add(p)
    db.commit()
    db.refresh(p)
    log.info(f"[OPS] preference upsert key={key}")
    return {"key": p.key, "value": p.value, "description": p.description}


def delete_preference(db: Session, key: str) -> bool:
    p = db.query(Preference).filter(Preference.key == key).first()
    if not p:
        return False
    db.delete(p)
    db.commit()
    log.info(f"[OPS] preference deleted key={key}")
    return True
