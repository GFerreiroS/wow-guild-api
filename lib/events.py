from datetime import date, datetime, time, timedelta
from typing import List, Optional

from fastapi import HTTPException
from sqlmodel import Session, select

import lib.db as db
import lib.schemas as schema


def get_event(event_id: int, session: Session) -> db.Event:
    ev = session.get(db.Event, event_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")
    return ev


def create_event(payload: schema.EventCreate, session: Session) -> db.Event:
    ev = db.Event(
        title=payload.title,
        description=payload.description,
        start_time=payload.start_time,
        end_time=payload.end_time,
        created_by=payload.created_by,
    )
    session.add(ev)
    session.commit()
    session.refresh(ev)
    return ev


def update_event(
    event_id: int, payload: schema.EventBase, session: Session
) -> db.Event:
    ev = session.get(db.Event, event_id)
    if not ev:
        raise HTTPException(404, "Event not found")
    ev.title = payload.title
    ev.description = payload.description
    ev.start_time = payload.start_time
    ev.end_time = payload.end_time
    session.add(ev)
    session.commit()
    session.refresh(ev)
    return ev


def delete_event(event_id: int, session: Session) -> dict:
    ev = session.get(db.Event, event_id)
    if not ev:
        raise HTTPException(404, "Event not found")
    session.delete(ev)
    session.commit()
    return {"status": "deleted", "event_id": event_id}


def list_events(
    period: Optional[str], start: Optional[date], session: Session
) -> List[db.Event]:
    # determine lower bound
    if start:
        lower = datetime.combine(start, time.min)
    else:
        lower = datetime.now()

    # base query: events starting at or after lower
    q = select(db.Event).where(db.Event.start_time >= lower)

    # apply window if requested
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

    results = session.exec(q).all()
    return list(results)


def sign_up_event(
    event_id: int, payload: schema.SignUpCreate, session: Session
) -> db.EventSignUp:
    # ensure event exists
    ev = session.get(db.Event, event_id)
    if not ev:
        raise HTTPException(404, "Event not found")

    # ensure user exists
    user = session.get(db.User, payload.user_id)
    if not user:
        raise HTTPException(404, "User not found")

    # no double‐signups
    existing = session.exec(
        select(db.EventSignUp)
        .where(db.EventSignUp.event_id == event_id)
        .where(db.EventSignUp.user_id == payload.user_id)
    ).first()
    if existing:
        raise HTTPException(400, "Already signed up")

    signup = db.EventSignUp(event_id=event_id, user_id=payload.user_id)
    session.add(signup)
    session.commit()
    session.refresh(signup)
    return signup
