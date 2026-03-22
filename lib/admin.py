import os

from fastapi import FastAPI
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from sqlmodel import Session
from starlette.requests import Request

import lib.db as db
import lib.security as security


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = form.get("username", "")
        password = form.get("password", "")
        with Session(db.engine) as session:
            user = security.authenticate_user(username, password, session)
            if not user or user.role not in ("owner", "administrator"):
                return False
        request.session["admin_user"] = username
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return "admin_user" in request.session


# ---------------------------------------------------------------------------
# Model views
# ---------------------------------------------------------------------------

class UserAdmin(ModelView, model=db.User):
    name = "User"
    name_plural = "Users"
    icon = "fa-solid fa-user"
    column_list = [db.User.id, db.User.username, db.User.role, db.User.created_at]
    column_searchable_list = [db.User.username]
    column_sortable_list = [db.User.username, db.User.role, db.User.created_at]
    column_default_sort = [(db.User.created_at, True)]
    form_excluded_columns = [db.User.password, db.User.created_at]
    can_create = False  # use POST /api/users
    can_delete = False  # sensitive — use API


class GuildMemberAdmin(ModelView, model=db.GuildMember):
    name = "Guild Member"
    name_plural = "Guild Members"
    icon = "fa-solid fa-shield-halved"
    column_list = [
        db.GuildMember.character_id,
        db.GuildMember.name,
        db.GuildMember.realm,
        db.GuildMember.level,
        db.GuildMember.race,
        db.GuildMember.clazz,
        db.GuildMember.faction,
        db.GuildMember.rank,
        db.GuildMember.fetched_at,
    ]
    column_searchable_list = [db.GuildMember.name, db.GuildMember.realm]
    column_sortable_list = [db.GuildMember.name, db.GuildMember.level, db.GuildMember.rank]
    column_default_sort = [(db.GuildMember.rank, False)]
    can_create = False  # synced from Blizzard via POST /api/guild/roster/update
    can_edit = False
    can_delete = False


class EventAdmin(ModelView, model=db.Event):
    name = "Event"
    name_plural = "Events"
    icon = "fa-solid fa-calendar-days"
    column_list = [db.Event.id, db.Event.title, db.Event.start_time, db.Event.end_time, db.Event.created_by]
    column_searchable_list = [db.Event.title]
    column_sortable_list = [db.Event.title, db.Event.start_time, db.Event.end_time]
    column_default_sort = [(db.Event.start_time, True)]


class EventSignUpAdmin(ModelView, model=db.EventSignUp):
    name = "Sign-up"
    name_plural = "Sign-ups"
    icon = "fa-solid fa-clipboard-list"
    column_list = [
        db.EventSignUp.id,
        db.EventSignUp.event_id,
        db.EventSignUp.user_id,
        db.EventSignUp.status,
        db.EventSignUp.signed_at,
    ]
    column_sortable_list = [db.EventSignUp.signed_at, db.EventSignUp.status]
    column_default_sort = [(db.EventSignUp.signed_at, True)]
    can_create = False
    can_edit = False


class ExpansionAdmin(ModelView, model=db.Expansion):
    name = "Expansion"
    name_plural = "Expansions"
    icon = "fa-solid fa-dragon"
    column_list = [db.Expansion.id, db.Expansion.name]
    column_searchable_list = [db.Expansion.name]
    can_create = False
    can_edit = False
    can_delete = False


class InstanceAdmin(ModelView, model=db.Instance):
    name = "Instance"
    name_plural = "Instances"
    icon = "fa-solid fa-dungeon"
    column_list = [
        db.Instance.blizzard_id,
        db.Instance.name,
        db.Instance.instance_type,
        db.Instance.is_current_season,
        db.Instance.expansion_id,
    ]
    column_searchable_list = [db.Instance.name]
    column_sortable_list = [db.Instance.name, db.Instance.instance_type, db.Instance.is_current_season]
    can_create = False
    can_edit = False
    can_delete = False


class EncounterAdmin(ModelView, model=db.Encounter):
    name = "Encounter"
    name_plural = "Encounters"
    icon = "fa-solid fa-skull-crossbones"
    column_list = [db.Encounter.id, db.Encounter.name, db.Encounter.instance_id, db.Encounter.sort_order]
    column_searchable_list = [db.Encounter.name]
    column_sortable_list = [db.Encounter.name, db.Encounter.sort_order]
    can_create = False
    can_edit = False
    can_delete = False


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def setup_admin(app: FastAPI) -> None:
    auth_backend = AdminAuth(secret_key=os.getenv("JWT_SECRET_KEY", "change-me"))
    admin = Admin(
        app,
        engine=db.engine,
        authentication_backend=auth_backend,
        title="Guild Admin",
        base_url="/admin",
    )
    admin.add_view(UserAdmin)
    admin.add_view(GuildMemberAdmin)
    admin.add_view(EventAdmin)
    admin.add_view(EventSignUpAdmin)
    admin.add_view(ExpansionAdmin)
    admin.add_view(InstanceAdmin)
    admin.add_view(EncounterAdmin)
