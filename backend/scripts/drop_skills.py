# cd /Users/aspen/Desktop/capstone_frontend/backend
# PYTHONPATH=. .venv/bin/python -c "
import asyncio
from sqlalchemy import select
from db.engine import async_session
from db.models import Skill
from services import skill_service

NAMES_TO_DELETE = {'KYC-Report-Generation', 'Generate-KYC-Report'}

async def main():
    async with async_session() as s:
        rows = (await s.execute(
            select(Skill).where(Skill.display_name.in_(NAMES_TO_DELETE))
        )).scalars().all()
        if not rows:
            print('No matching skills.')
            return
        for skill in rows:
            slug, was_builtin = skill.slug, skill.is_builtin
            skill.is_builtin = False
            await s.flush()
            ok = await skill_service.delete_skill(s, slug)
            print(f'{slug} (builtin={was_builtin}) -> {"deleted" if ok else "skipped"}')
        await s.commit()

asyncio.run(main())