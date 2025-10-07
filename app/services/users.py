from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from ..models import User


def get_or_create_user(session: Session, telegram_id: int) -> User:
    user = session.query(User).filter_by(telegram_id=telegram_id).one_or_none()
    if user is None:
        user = User(telegram_id=telegram_id)
        session.add(user)
        session.flush()
    return user


def update_timezone(session: Session, telegram_id: int, tz: str) -> User:
    user = get_or_create_user(session, telegram_id)
    user.tz = tz
    return user
