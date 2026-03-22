import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional, cast

from fastapi import HTTPException
from sqlmodel import Session, select

import lib.db as db
import lib.schemas as schema

logger = logging.getLogger(__name__)


def _make_signup_read(signup: db.EventSignUp, users: dict[int, db.User]) -> schema.SignUpRead:
    username = users[signup.user_id].username if signup.user_id in users else "unknown"
    # signup.status may be a plain str (SQLite returns raw column value) or a SignUpStatus enum
    status_val = signup.status if isinstance(signup.status, str) else signup.status.value
    return schema.SignUpRead(
        id=cast(int, signup.id),
        event_id=signup.event_id,
        user_id=signup.user_id,
        username=username,
        signed_at=signup.signed_at,
        status=schema.SignUpStatus(status_val),
    )


def _load_signups_for_event(event_id: int, session: Session) -> list[schema.SignUpRead]:
    rows = session.exec(
        select(db.EventSignUp).where(db.EventSignUp.event_id == event_id)
    ).all()
    user_ids = {su.user_id for su in rows}
    users: dict[int, db.User] = {}
    if user_ids:
        users = {
            u.id: u  # type: ignore[index]
            for u in session.exec(select(db.User).where(db.User.id.in_(user_ids))).all()
        }
    return [_make_signup_read(su, users) for su in rows]


def get_event(event_id: int, session: Session) -> schema.EventRead:
    ev = session.get(db.Event, event_id)
    if not ev:
        raise HTTPException(404, "Event not found")

    signups = _load_signups_for_event(event_id, session)
    return schema.EventRead(
        id=cast(int, ev.id),
        title=ev.title,
        description=ev.description,
        start_time=ev.start_time,
        end_time=ev.end_time,
        created_by=ev.created_by,
        signups=signups,
    )


def create_event(
    payload: schema.EventCreate, session: Session, *, created_by: int
) -> schema.EventRead:
    ev = db.Event(
        title=payload.title,
        description=payload.description,
        start_time=payload.start_time,
        end_time=payload.end_time,
        created_by=created_by,
    )
    session.add(ev)
    session.commit()
    session.refresh(ev)
    return get_event(cast(int, ev.id), session)


def update_event(
    event_id: int, payload: schema.EventBase, session: Session
) -> schema.EventRead:
    ev = session.get(db.Event, event_id)
    if not ev:
        raise HTTPException(404, "Event not found")
    ev.title = payload.title
    ev.description = payload.description
    ev.start_time = payload.start_time
    ev.end_time = payload.end_time
    session.add(ev)
    session.commit()
    return get_event(event_id, session)


def delete_event(event_id: int, session: Session) -> dict:
    ev = session.get(db.Event, event_id)
    if not ev:
        raise HTTPException(404, "Event not found")
    session.delete(ev)
    session.commit()
    return {"status": "deleted", "event_id": event_id}


def list_events(
    period: Optional[str],
    start: Optional[date],
    skip: int,
    limit: int,
    session: Session,
) -> List[schema.EventRead]:
    lower = datetime.combine(start, time.min) if start else datetime.now(timezone.utc)

    q = select(db.Event).where(db.Event.start_time >= lower)

    if period == "day":
        upper = lower + timedelta(days=1)
    elif period == "week":
        upper = lower + timedelta(weeks=1)
    elif period == "month":
        upper = lower + timedelta(days=30)
    else:
        upper = None

    if upper:
        q = q.where(db.Event.start_time < upper)

    q = q.offset(skip).limit(limit)
    ev_rows = session.exec(q).all()

    if not ev_rows:
        return []

    # Batch-load signups and users to avoid N+1 queries
    ev_ids = [ev.id for ev in ev_rows]
    all_signups = session.exec(
        select(db.EventSignUp).where(db.EventSignUp.event_id.in_(ev_ids))
    ).all()

    user_ids = {su.user_id for su in all_signups}
    users: dict[int, db.User] = {}
    if user_ids:
        users = {
            u.id: u  # type: ignore[index]
            for u in session.exec(select(db.User).where(db.User.id.in_(user_ids))).all()
        }

    signups_by_event: dict[int, list[db.EventSignUp]] = {}
    for su in all_signups:
        signups_by_event.setdefault(su.event_id, []).append(su)

    out: list[schema.EventRead] = []
    for ev in ev_rows:
        ev_signups = [
            _make_signup_read(su, users)
            for su in signups_by_event.get(cast(int, ev.id), [])
        ]
        out.append(
            schema.EventRead(
                id=cast(int, ev.id),
                title=ev.title,
                description=ev.description,
                start_time=ev.start_time,
                end_time=ev.end_time,
                created_by=ev.created_by,
                signups=ev_signups,
            )
        )
    return out


def sign_up_event(
    event_id: int,
    payload: schema.SignUpCreate,
    session: Session,
    *,
    actor: db.User,
) -> schema.SignUpRead:
    ev = session.get(db.Event, event_id)
    if not ev:
        raise HTTPException(404, "Event not found")

    if actor.id is None:
        raise HTTPException(400, "Authenticated user is missing an identifier")

    target_user_id = payload.user_id
    actor_id = cast(int, actor.id)

    if target_user_id != actor_id and actor.role not in ("owner", "administrator"):
        raise HTTPException(403, "Forbidden: cannot sign up other users")

    user = session.get(db.User, target_user_id)
    if not user:
        raise HTTPException(404, "User not found")

    existing = session.exec(
        select(db.EventSignUp)
        .where(db.EventSignUp.event_id == event_id)
        .where(db.EventSignUp.user_id == target_user_id)
    ).first()
    if existing:
        raise HTTPException(400, "Already signed up")

    status_val = payload.status if payload.status is not None else schema.SignUpStatus.Assist
    signup = db.EventSignUp(
        event_id=event_id,
        user_id=target_user_id,
        status=db.SignUpStatus(status_val.value),
    )
    session.add(signup)
    session.commit()
    session.refresh(signup)
    return _make_signup_read(signup, {target_user_id: user})


def update_signup(
    event_id: int,
    payload: schema.SignUpUpdate,
    session: Session,
    *,
    actor: db.User,
) -> schema.SignUpRead:
    ev = session.get(db.Event, event_id)
    if not ev:
        raise HTTPException(404, "Event not found")

    actor_id = cast(int, actor.id)
    target_user_id = payload.user_id

    if target_user_id != actor_id and actor.role not in ("owner", "administrator"):
        raise HTTPException(403, "Forbidden: cannot update other users' signups")

    existing = session.exec(
        select(db.EventSignUp)
        .where(db.EventSignUp.event_id == event_id)
        .where(db.EventSignUp.user_id == target_user_id)
    ).first()
    if not existing:
        raise HTTPException(404, "Signup not found")

    existing.status = db.SignUpStatus(payload.status.value)
    session.add(existing)
    session.commit()
    session.refresh(existing)

    user = session.get(db.User, target_user_id)
    return _make_signup_read(existing, {target_user_id: user} if user else {})


def delete_signup(
    event_id: int,
    user_id: int,
    session: Session,
    *,
    actor: db.User,
) -> dict:
    ev = session.get(db.Event, event_id)
    if not ev:
        raise HTTPException(404, "Event not found")

    actor_id = cast(int, actor.id)
    if user_id != actor_id and actor.role not in ("owner", "administrator"):
        raise HTTPException(403, "Forbidden: cannot delete other users' signups")

    existing = session.exec(
        select(db.EventSignUp)
        .where(db.EventSignUp.event_id == event_id)
        .where(db.EventSignUp.user_id == user_id)
    ).first()
    if not existing:
        raise HTTPException(404, "Signup not found")

    session.delete(existing)
    session.commit()
    return {"status": "deleted", "event_id": event_id, "user_id": user_id}
