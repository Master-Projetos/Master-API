import asyncio
from getpass import getpass

from sqlalchemy import or_, select

from app.core.database import async_session, engine
from app.core.security import get_password_hash
from app.modules.user.model import User, UserRole


async def main() -> None:
    async with async_session() as session:
        existing_admin = await session.scalar(
            select(User).where(User.role == UserRole.ADMIN)
        )
        if existing_admin:
            print('Já existe um admin. Nada foi feito.')
            return

        username = input('Username: ').strip()
        email = input('Email: ').strip().lower()
        password = getpass('Senha (mín. 8 caracteres): ')
        password_confirmation = getpass('Confirme a senha: ')

        if not 3 <= len(username) <= 50:
            print('Username deve ter entre 3 e 50 caracteres.')
            return

        if '@' not in email:
            print('Email inválido.')
            return

        if len(password) < 8 or password != password_confirmation:
            print('Senha curta demais ou as senhas não conferem.')
            return

        duplicate_user = await session.scalar(
            select(User).where(
                or_(User.username == username, User.email == email)
            )
        )
        if duplicate_user:
            print('Já existe um usuário com esse username ou email.')
            return

        session.add(
            User(
                username=username,
                email=email,
                hashed_password=get_password_hash(password),
                role=UserRole.ADMIN,
            )
        )
        await session.commit()
        print(f'Admin {username} criado.')


if __name__ == '__main__':
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
