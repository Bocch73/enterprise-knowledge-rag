"""Securely create or promote a local administrator without password arguments."""

import asyncio
from getpass import getpass

from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.core.event_loop import configure_event_loop_policy
from app.db.session import Database
from app.modules.identity.models import Role
from app.modules.identity.schemas import UserRegister
from app.modules.identity.service import get_user_by_email, register_user


async def create_or_promote_admin(
    email: str,
    display_name: str,
    password: str,
    settings: Settings | None = None,
) -> None:
    """Create a member when needed, then grant the global administrator role."""
    database = Database(settings or get_settings())
    try:
        async with database.session_factory() as session:
            user = await get_user_by_email(session, email)
            if user is None:
                user = await register_user(
                    session,
                    UserRegister(email=email, display_name=display_name, password=password),
                )
            if not user.has_role("admin"):
                admin_role = await session.scalar(select(Role).where(Role.code == "admin"))
                if admin_role is None:
                    raise RuntimeError("admin role is missing; apply database migrations")
                user.roles.append(admin_role)
                await session.commit()
    finally:
        await database.dispose()


def main() -> None:
    """Prompt interactively so plaintext passwords never appear in shell history."""
    email = input("管理员邮箱：").strip()
    display_name = input("显示名称：").strip()
    password = getpass("管理员密码（至少 12 个字符）：")
    confirmation = getpass("再次输入管理员密码：")
    if password != confirmation:
        raise SystemExit("两次密码不一致，未创建管理员。")

    configure_event_loop_policy()
    asyncio.run(create_or_promote_admin(email, display_name, password))
    print("管理员账户已创建或已提升权限。")


if __name__ == "__main__":
    main()
