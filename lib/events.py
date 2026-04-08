import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional, cast

from fastapi import HTTPException
from sqlmodel import Session, select

import lib.db as db
import lib.schemas as schema

logger = logging.getLogger(__name__)


def _make_signup_read(
    signup: db.EventSignUp,
    users: dict[int, db.User],
    characters: dict[int, db.GuildMember],
) -> schema.SignUpRead:
    username = users[signup.user_id].username if signup.user_id in users else "unknown"
    status_val = signup.status if isinstance(signup.status, str) else signup.status.value
    char = characters.get(signup.character_id) if signup.character_id else None
    return schema.SignUpRead(
        id=cast(int, signup.id),
        event_id=signup.event_id,
        user_id=signup.user_id,
        username=username,
        character_id=signup.character_id,
        character_name=char.name if char else None,
        character_realm=char.realm if char else None,
        signed_at=signup.signed_at,
        status=schema.SignUpStatus(status_val),
    )


def _load_signups_for_event(event_id: int, session: Session) -> list[schema.SignUpRead]:
    rows = session.exec(
        select(db.EventSignUp).where(db.EventSignUp.event_id == event_id)
    ).all()
    user_ids = {su.user_id for su in rows}
    char_ids = {su.character_id for su in rows if su.character_id}
    users: dict[int, db.User] = {}
    characters: dict[int, db.GuildMember] = {}
    if user_ids:
        users = {
            u.id: u  # type: ignore[index]
            for u in session.exec(select(db.User).where(db.User.id.in_(user_ids))).all()
        }
    if char_ids:
        characters = {
            gm.character_id: gm
            for gm in session.exec(select(db.GuildMember).where(db.GuildMember.character_id.in_(char_ids))).all()
        }
    return [_make_signup_read(su, users, characters) for su in rows]


def _instance_fields(blizzard_id: Optional[int], session: Session) -> tuple[Optional[str], Optional[str]]:
    """Return (instance_name, instance_img) for a given blizzard_id, or (None, None)."""
    if not blizzard_id:
        return None, None
    inst = session.exec(select(db.Instance).where(db.Instance.blizzard_id == blizzard_id)).first()
    return (inst.name, inst.img) if inst else (None, None)


def _event_read(ev: db.Event, signups: list[schema.SignUpRead], instance_name: Optional[str], instance_img: Optional[str]) -> schema.EventRead:
    return schema.EventRead(
        id=cast(int, ev.id),
        title=ev.title,
        description=ev.description,
        start_time=ev.start_time,
        end_time=ev.end_time,
        created_by=ev.created_by,
        instance_blizzard_id=ev.instance_blizzard_id,
        instance_name=instance_name,
        instance_img=instance_img,
        signups=signups,
    )


def get_event(event_id: int, session: Session) -> schema.EventRead:
    ev = session.get(db.Event, event_id)
    if not ev:
        raise HTTPException(404, "Event not found")
    signups = _load_signups_for_event(event_id, session)
    name, img = _instance_fields(ev.instance_blizzard_id, session)
    return _event_read(ev, signups, name, img)


def create_event(
    payload: schema.EventCreate, session: Session, *, created_by: int
) -> schema.EventRead:
    # Prevent same user from scheduling the same raid twice in the same hour
    if payload.instance_blizzard_id is not None:
        hour_start = payload.start_time.replace(minute=0, second=0, microsecond=0)
        hour_end = hour_start + timedelta(hours=1)
        conflict = session.exec(
            select(db.Event).where(
                db.Event.created_by == created_by,
                db.Event.instance_blizzard_id == payload.instance_blizzard_id,
                db.Event.start_time >= hour_start,
                db.Event.start_time < hour_end,
            )
        ).first()
        if conflict:
            raise HTTPException(
                400,
                "You already have an event for this raid at this hour. "
                "Choose a different time or a different raid.",
            )

    ev = db.Event(
        title=payload.title,
        description=payload.description,
        start_time=payload.start_time,
        end_time=payload.end_time,
        created_by=created_by,
        instance_blizzard_id=payload.instance_blizzard_id,
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
    ev.instance_blizzard_id = payload.instance_blizzard_id
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
    char_ids = {su.character_id for su in all_signups if su.character_id}
    users: dict[int, db.User] = {}
    characters: dict[int, db.GuildMember] = {}
    if user_ids:
        users = {
            u.id: u  # type: ignore[index]
            for u in session.exec(select(db.User).where(db.User.id.in_(user_ids))).all()
        }
    if char_ids:
        characters = {
            gm.character_id: gm
            for gm in session.exec(select(db.GuildMember).where(db.GuildMember.character_id.in_(char_ids))).all()
        }

    signups_by_event: dict[int, list[db.EventSignUp]] = {}
    for su in all_signups:
        signups_by_event.setdefault(su.event_id, []).append(su)

    # Batch-load instance data
    inst_ids = {ev.instance_blizzard_id for ev in ev_rows if ev.instance_blizzard_id}
    instances: dict[int, db.Instance] = {}
    if inst_ids:
        instances = {
            i.blizzard_id: i
            for i in session.exec(select(db.Instance).where(db.Instance.blizzard_id.in_(inst_ids))).all()
        }

    out: list[schema.EventRead] = []
    for ev in ev_rows:
        ev_signups = [
            _make_signup_read(su, users, characters)
            for su in signups_by_event.get(cast(int, ev.id), [])
        ]
        inst = instances.get(ev.instance_blizzard_id) if ev.instance_blizzard_id else None
        out.append(_event_read(ev, ev_signups, inst.name if inst else None, inst.img if inst else None))
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

    # Resolve character: use provided, fall back to user's primary, or None
    character_id = payload.character_id
    if character_id is None:
        character_id = user.primary_character_id
    if character_id is not None:
        gm = session.get(db.GuildMember, character_id)
        if not gm or gm.user_id != target_user_id:
            raise HTTPException(400, "Character does not belong to this user")

    status_val = payload.status if payload.status is not None else schema.SignUpStatus.Assist
    signup = db.EventSignUp(
        event_id=event_id,
        user_id=target_user_id,
        character_id=character_id,
        status=db.SignUpStatus(status_val.value),
    )
    session.add(signup)
    session.commit()
    session.refresh(signup)
    chars = {character_id: session.get(db.GuildMember, character_id)} if character_id else {}
    return _make_signup_read(signup, {target_user_id: user}, chars)


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
    if payload.character_id is not None:
        gm = session.get(db.GuildMember, payload.character_id)
        if not gm or gm.user_id != target_user_id:
            raise HTTPException(400, "Character does not belong to this user")
        existing.character_id = payload.character_id
    session.add(existing)
    session.commit()
    session.refresh(existing)

    user = session.get(db.User, target_user_id)
    chars = {}
    if existing.character_id:
        gm = session.get(db.GuildMember, existing.character_id)
        if gm:
            chars[existing.character_id] = gm
    return _make_signup_read(existing, {target_user_id: user} if user else {}, chars)


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
