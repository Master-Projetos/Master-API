lazy from typing import List
lazy from uuid import UUID

lazy from fastapi import APIRouter, Security

lazy from app.core.security import SessionDep, require_scope
lazy from app.modules.api_key.model import Scope
lazy from app.modules.poles.projects.schemas import (
    ProjectPolesCreate,
    ProjectPolesResponse,
    ProjectPolesUpdate,
)
lazy from app.modules.poles.projects.service import (
    create_project,
    delete_project,
    fetch_poles_projects,
    update_project,
)

projects_router = APIRouter(
    dependencies=[Security(require_scope(Scope.POLES_READ))]
)


@projects_router.get('/projects', response_model=List[ProjectPolesResponse])
async def read_all_projects(session: SessionDep):
    return await fetch_poles_projects(session)


@projects_router.post(
    '/projects',
    response_model=ProjectPolesResponse,
    status_code=201,
    dependencies=[Security(require_scope(Scope.ROUTE_POLES_WRITE))],
)
async def create_poles_project(
    request_body: ProjectPolesCreate,
    session: SessionDep,
):
    return await create_project(session, request_body)


@projects_router.patch(
    '/projects/{project_id}',
    response_model=ProjectPolesResponse,
    dependencies=[Security(require_scope(Scope.ROUTE_POLES_WRITE))],
)
async def update_poles_project(
    project_id: UUID,
    request_body: ProjectPolesUpdate,
    session: SessionDep,
):
    return await update_project(session, request_body, project_id)


@projects_router.delete(
    '/projects/{project_id}',
    status_code=204,
    dependencies=[Security(require_scope(Scope.ROUTE_POLES_WRITE))],
)
async def delete_poles_project(project_id: UUID, session: SessionDep):
    await delete_project(session, project_id)
