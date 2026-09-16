import logging
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from core.limiter import limiter
from core.constants import ALLOWED_RELATORIES
from .service import (
    run_export,
    treat_viabilidade,
    export_lock,
    export_status
    )
from .schemas import ReportSchema

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Relatorio"])

@router.get("/{relatory}/status")
@limiter.limit("200/minute")
def get_export_status(request: Request, relatory: str):
    status = export_status.get(relatory)
    if not status:
        logger.warning("relatory=%s: status requested but no export found", relatory)
        raise HTTPException(status_code=404, detail="No export found for the relatory")
    return status


@router.post("/{relatory}", response_model=ReportSchema)
@limiter.limit("2/minute")
def request_export(request: Request, relatory: str, background_tasks: BackgroundTasks):
    if relatory not in ALLOWED_RELATORIES:
        logger.warning("relatory=%s: export requested but not supported", relatory)
        raise HTTPException(status_code=400, detail="Relatory not supported")

    if export_lock.locked():
        logger.info("relatory=%s: export requested but another export is already running", relatory)
        raise HTTPException(status_code=409, detail="Another export is already running")

    logger.info("relatory=%s: export enqueued", relatory)
    background_tasks.add_task(run_export, relatory)
    return {"status": "processing", "relatory" : relatory}


@router.get("/viability")
@limiter.limit("10/minute")
def get_data(request: Request):
    viability_json = treat_viabilidade()
    if viability_json is None:
        logger.warning("viability data requested but not found")
        raise HTTPException(status_code=400, detail="Relatory has not find")

    return viability_json