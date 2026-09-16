from fastapi import APIRouter, BackgroundTasks, HTTPException
from core.constants import ALLOWED_RELATORIES
from .service import (
    run_export,
    treat_viabilidade,
    export_lock, 
    export_status
    )
from .schemas import ReportSchema

router = APIRouter(tags=["Relatorio"])


@router.get("/{relatory}/status")
def get_export_status(relatory: str):
    status = export_status.get(relatory)
    if not status:
        raise HTTPException(status_code=404, detail="No export found for the relatory")
    return status


@router.post("/{relatory}", response_model=ReportSchema)
def request_export(relatory: str, background_tasks: BackgroundTasks):
    if relatory not in ALLOWED_RELATORIES:
        raise HTTPException(status_code=400, detail="Relatory not supported")
    
    if export_lock.locked():
        raise HTTPException(status_code=409, detail="Another export is already running")
    
    background_tasks.add_task(run_export, relatory)
    return {"status": "processing", "relatory" : relatory}


@router.get("/viability")
def get_data():
    viability_json = treat_viabilidade()
    if viability_json is None:
        raise HTTPException(status_code=400, detail="Relatory has not find")
    
    return viability_json