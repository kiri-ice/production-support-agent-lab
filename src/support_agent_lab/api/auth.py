from __future__ import annotations

from typing import Annotated

from fastapi import Header, HTTPException, status
from pydantic import BaseModel


class DemoActor(BaseModel):
    user_id: str
    roles: list[str]

    @property
    def is_admin(self) -> bool:
        return "admin" in self.roles


def get_demo_actor(
    x_demo_user: Annotated[str | None, Header(alias="X-Demo-User")] = None,
    x_demo_role: Annotated[str | None, Header(alias="X-Demo-Role")] = None,
) -> DemoActor:
    roles = [role.strip() for role in (x_demo_role or "user").split(",") if role.strip()]
    return DemoActor(user_id=x_demo_user or "user_demo", roles=roles)


def require_same_user(request_user_id: str, actor: DemoActor) -> None:
    if request_user_id != actor.user_id and not actor.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Request user_id must match authenticated demo actor",
        )


def require_admin(actor: DemoActor) -> None:
    if not actor.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required. In demo mode pass X-Demo-Role: admin.",
        )

