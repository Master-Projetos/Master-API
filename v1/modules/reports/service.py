import os
import json
import logging
import unicodedata
from datetime import datetime, timedelta
import threading
import requests
import pandas as pd
from core.settings import get_settings
from core.constants import ALLOWED_RELATORIES, GEOGRID_URL, REGION_CITIES

logger = logging.getLogger(__name__)

settings = get_settings()

GEOGRID_USER = settings.GEOGRID_USER
GEOGRID_PASS = settings.GEOGRID_PASSWORD
SESSION_TTL = settings.SESSION_TTL_MINUTES

_session : requests.Session | None = None
_last_login_at : datetime | None = None

GEOGRID_API = GEOGRID_URL.rstrip("/") + "/api/v3"
GEOGRID_VERSION = "199.7"
REGISTROS_POR_PAGINA = 1000

# Map from the report's field names to the display column names the rest of the
# pipeline (treat_viabilidade / dashboard) already expects.
FIELD_MAP = {
    "sigla": "Sigla",
    "latitude": "Latitude",
    "longitude": "Longitude",
    "cidade": "Cidade",
    "descricaoRecipienteTipo": "Tipo",
    "quantidadeEquipamentos": "Quantidade equip.",
    "quantidadePortas": "Quantidade portas",
    "quantidadePortasOcupadas": "Portas ocupadas",
    "quantidadePortasLivres": "Portas livres",
    "quantidadePortasClienteAtendimento": "Portas atendimento cliente",
}

def _normalize(text: str) -> str:
    if not isinstance(text, str):
        text = ""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return text.strip().lower()


CITY_TO_REGION = {
    _normalize(city): region
    for region, cities in REGION_CITIES.items()
    for city in cities
}


def get_region(cidade: str) -> str:
    normalized = _normalize(cidade)
    if not normalized:
        return "Indeterminado"
    return CITY_TO_REGION.get(normalized, "Indeterminado")


export_lock = threading.Lock()

# In-memory status store, keyed by relatory name.
# Fine for a single-process app with one export at a time (export_lock);
# TODO: Use regis insted of a dict
export_status = {}

def set_status(relatory: str, step: str, status: str = "processing"):
    export_status[relatory] = {"step": step, "status": status}


def login():
    logger.info("Logging in to Geogrid API")
    session = requests.Session()
    session.headers.update({
        "Accept": "application/json",
        "Geogrid-Version": GEOGRID_VERSION,
    })
    resp = session.post(f"{GEOGRID_API}/autenticar", json={
        "usuario": GEOGRID_USER,
        "senha": GEOGRID_PASS,
        "codigoSeguranca": "",
        "dadosDispositivo": {},
        "hashDispositivo": None,
    }, timeout=60)
    resp.raise_for_status()

    token = resp.json().get("autenticacao")
    if not token:
        logger.error("Login failed: no authentication token returned")
        raise RuntimeError("Login failed: no authentication token returned")

    session.headers["Authorization"] = token
    logger.info("Login succeeded")
    return session

def ensure_session() -> requests.Session:
    global _session, _last_login_at

    expired = (
        _last_login_at is None
        or datetime.now() - _last_login_at > timedelta(minutes=SESSION_TTL)
    )
    if _session is None or expired:
        logger.info("Session missing or expired, creating a new one")
        _session = login()
        _last_login_at = datetime.now()

    return _session


def export_relatory(relatory: str, download_dir: str = None):
    if relatory not in ALLOWED_RELATORIES:
        raise RuntimeError("This relatory doesn't have support yet, try a valid one")

    if download_dir is None:
        PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        download_dir = os.path.join(PROJECT_ROOT, "data")
    os.makedirs(download_dir, exist_ok=True)

    logger.info("Starting export for relatory=%s", relatory)
    set_status(relatory, step="login")
    session = ensure_session()

    registros = []
    pagina = 1
    total_paginas = None
    while True:
        resp = session.get(f"{GEOGRID_API}/relatorios/{relatory}", params={
            "pagina": pagina,
            "registrosPorPagina": REGISTROS_POR_PAGINA,
            "consultarTotais": "S" if pagina == 1 else "N",
            "modoProjeto[]": "N",
        }, timeout=120)
        resp.raise_for_status()
        data = resp.json()

        pagina_registros = data.get("registros", [])
        registros.extend(pagina_registros)

        if total_paginas is None:
            total = int(data.get("totalRegistros", 0))
            total_paginas = max(1, -(-total // REGISTROS_POR_PAGINA))  # ceil

        set_status(relatory, step=f"baixando pagina {pagina}/{total_paginas}")
        logger.info("relatory=%s: downloaded page %s/%s", relatory, pagina, total_paginas)

        if pagina >= total_paginas or not pagina_registros:
            break
        pagina += 1

    file_path = os.path.join(download_dir, f"{relatory}.json")
    with open(file_path, "w", encoding="utf-8") as fh:
        json.dump(registros, fh, ensure_ascii=False)

    set_status(relatory, step="Concluido", status="Done")
    logger.info("relatory=%s: export finished with %s records", relatory, len(registros))


def run_export(relatory: str):
    global _session
    with export_lock:
        try:
            export_relatory(relatory)
        except requests.HTTPError as error:
            if error.response is not None and error.response.status_code in (401, 403):
                logger.warning("relatory=%s: session rejected (%s), invalidating cached session", relatory, error.response.status_code)
                _session = None
            logger.exception("relatory=%s: export failed", relatory)
            set_status(relatory, step=f"Falha: {error}", status="Error")
            raise
        except Exception as error:
            logger.exception("relatory=%s: export failed", relatory)
            set_status(relatory, step=f"Falha: {error}", status="Error")
            raise


def treat_viabilidade():
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    data_dir = os.path.join(PROJECT_ROOT, "data")
    file_path = os.path.join(data_dir, "viabilidade.json")

    if not os.path.isfile(file_path):
        logger.warning("treat_viabilidade: file not found at %s", file_path)
        return None

    with open(file_path, encoding="utf-8") as fh:
        registros = json.load(fh)

    raw_df = pd.DataFrame(registros)
    raw_df = raw_df[[c for c in FIELD_MAP if c in raw_df.columns]].rename(columns=FIELD_MAP)

    mask_cto = raw_df["Tipo"].str.contains("CTO", case=False, na=False)

    cto_df = raw_df[mask_cto].copy()
    ceo_df = raw_df[~mask_cto].copy()

    cols_numericas = [
        "Quantidade equip.", "Quantidade portas", "Portas ocupadas",
        "Portas livres", "Portas atendimento cliente",
    ]
    for df in (cto_df, ceo_df):
        df[cols_numericas] = df[cols_numericas].apply(pd.to_numeric, errors="coerce")
        df["Regiao"] = df["Cidade"].apply(get_region)

    cto_df = cto_df.dropna(subset=cols_numericas, how="all")
    cto_df[cols_numericas] = cto_df[cols_numericas].fillna(0)

    cols_tabela = ["Sigla", "Latitude", "Longitude", "Cidade", "Regiao"] + cols_numericas
    cto_table = cto_df[cols_tabela].copy().fillna("")

    ceo_df = ceo_df.dropna(subset=cols_numericas, how="all")
    ceo_df[cols_numericas] = ceo_df[cols_numericas].fillna(0)
    ceo_table = ceo_df[cols_tabela].copy().fillna("")

    estatisticas = {
        "Equipamentos": int(cto_table["Quantidade equip."].sum()),
        "Portas": int(cto_table["Quantidade portas"].sum()),
        "Portas ocupadas": int(cto_table["Portas ocupadas"].sum()),
        "Portas livres": int(cto_table["Portas livres"].sum()),
        "Portas atendimento cliente": int(cto_table["Portas atendimento cliente"].sum()),
    }

    return {
        "estatisticas": estatisticas,
        "ctos": _group_by_region(cto_table),
        "ceos": _group_by_region(ceo_table),
    }


def _group_by_region(table: pd.DataFrame) -> dict:
    return {
        regiao: {
            cidade: cidade_group.drop(columns=["Regiao", "Cidade"]).to_dict(orient="records")
            for cidade, cidade_group in regiao_group.groupby("Cidade")
        }
        for regiao, regiao_group in table.groupby("Regiao")
    }
