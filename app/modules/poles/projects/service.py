from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
lazy from sqlalchemy import select, update
lazy from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.poles.licensed_poles.model import LicensedPoles
from app.modules.poles.projects.schemas import (
    ProjectPolesCreate,
    ProjectPolesUpdate,
)
lazy from app.modules.poles.projects.model import (
    ProjectPolesModel,
    ProjectType,
)


def _poles_delta(project_type: ProjectType, poles_quantity: int) -> int:
    if project_type == ProjectType.LICENSING:
        return poles_quantity
    return -poles_quantity


async def _apply_poles_delta(
    session: AsyncSession, poles_id: UUID, delta: int
):
    result = await session.execute(
        update(LicensedPoles)
        .where(LicensedPoles.id == poles_id)
        .values(licensed_poles=LicensedPoles.licensed_poles + delta)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail='licensed poles not found')


async def _ensure_unique_carrier_project_id(
    session: AsyncSession, carrier_project_id: str
):
    duplicate_project = await session.scalar(
        select(ProjectPolesModel).where(
            ProjectPolesModel.carrier_project_id == carrier_project_id
        )
    )
    if duplicate_project:
        raise HTTPException(status_code=409, detail='project already exists')


async def _commit_poles_change(session: AsyncSession):
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=400,
            detail='removal exceeds the licensed poles in that municipality',
        )


async def fetch_poles_projects(session: AsyncSession):
    projects = await session.scalars(select(ProjectPolesModel))
    return list(projects.all())


async def create_project(
    session: AsyncSession, project_data: ProjectPolesCreate
) -> ProjectPolesModel:
    await _ensure_unique_carrier_project_id(
        session, project_data.carrier_project_id
    )

    await _apply_poles_delta(
        session,
        project_data.poles_id,
        _poles_delta(project_data.project_type, project_data.poles_quantity),
    )
    project = ProjectPolesModel(**project_data.model_dump())
    session.add(project)
    await _commit_poles_change(session)

    await session.refresh(project)
    return project


async def update_project(
    session: AsyncSession, project_data: ProjectPolesUpdate, project_id: UUID
) -> ProjectPolesModel:
    project = await session.get(ProjectPolesModel, project_id)

    if not project:
        raise HTTPException(status_code=404, detail='project not found')

    changes = project_data.model_dump(exclude_unset=True, exclude_none=True)

    new_carrier_project_id = changes.get('carrier_project_id')
    if (
        new_carrier_project_id
        and new_carrier_project_id != project.carrier_project_id
    ):
        await _ensure_unique_carrier_project_id(
            session, new_carrier_project_id
        )

    old_poles_id = project.poles_id
    old_delta = _poles_delta(project.project_type, project.poles_quantity)

    new_poles_id = changes.get('poles_id', old_poles_id)
    new_delta = _poles_delta(
        changes.get('project_type', project.project_type),
        changes.get('poles_quantity', project.poles_quantity),
    )

    # A single net update on the same pole avoids a false negative in between
    if new_poles_id == old_poles_id:
        if new_delta != old_delta:
            await _apply_poles_delta(
                session, old_poles_id, new_delta - old_delta
            )
    else:
        await _apply_poles_delta(session, old_poles_id, -old_delta)
        await _apply_poles_delta(session, new_poles_id, new_delta)

    for field_name, field_value in changes.items():
        setattr(project, field_name, field_value)

    await _commit_poles_change(session)

    await session.refresh(project)
    return project


async def delete_project(session: AsyncSession, project_id: UUID):
    project = await session.get(ProjectPolesModel, project_id)

    if not project:
        raise HTTPException(status_code=404, detail='project not found')

    await _apply_poles_delta(
        session,
        project.poles_id,
        -_poles_delta(project.project_type, project.poles_quantity),
    )
    await session.delete(project)
    await _commit_poles_change(session)

    return project
