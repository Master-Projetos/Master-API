"""Critical CTOs (few free ports in Geogrid) cross-checked with the attendants'
sheet, where each tab holds blocks of ports checked in the field per CTO."""

import logging
import re
import unicodedata
from io import BytesIO

import pandas as pd
import requests

from app.core.settings import get_settings
from app.modules.geogrid.service import get_cto_table

logger = logging.getLogger(__name__)

FETCH_TIMEOUT_SECONDS = 60

# 'DVL-CJ-207' -> city prefix + code letters + code number
PREFIXED_SIGLA_TOKENS = 3

# Synonym headers across the tabs -> standard name
RENAME_COLUMNS = {
    'MAC DO CLIENTE': 'MAC',
    'NOMECLATURA': 'NOMENCLATURA',
    'ENDEREÇO E ENDEREÇO E BAIRRO': 'ENDEREÇO E BAIRRO',
    'BAIRRO': 'ENDEREÇO E BAIRRO',
    'PORTA': 'PORTA CTO',
}

SHEET_COLUMNS = [
    'ABA',
    'OLT',
    'PORTA OLT',
    'PLACA E PORTA OLT',
    'PORTA CTO',
    'Offline',
    'MAC',
    'CONTRATO',
    'CÓDIGO',
    'NOME',
    'DATA',
    'TÉCNICO',
    'NOMENCLATURA',
    'ENDEREÇO E BAIRRO',
    'CIDADE',
    'ATENDENTE',
]

# Text typed in place of the data that does not mean there is a client
NO_INFO = {
    '',
    '-',
    '--',
    '*',
    'vaga',
    'porta vaga',
    'não caiu',
    'nao caiu',
    'caiu',
    'cancelado',
    'sem id',
    'sem código',
    'sem codigo',
    'sem cod',
    'não achei',
    'nao achei',
    'spliter',
    'sem informação',
    'sem informação.',
    'nan',
}

CLIENT_COLUMNS = ['MAC', 'CONTRATO', 'CÓDIGO', 'NOME']

STATUS_CLIENT = 'Com cliente'
STATUS_FREE = 'Livre'
STATUS_UNCHECKED = 'Não checada'

# City abbreviations / typos used in the sheet -> normalized city
CITY_ALIASES = {
    'sjc': 'sao jose dos campos',
    's.j dos campos': 'sao jose dos campos',
    'sj dos campos': 'sao jose dos campos',
    'dvl': 'divinopolis',
    'pimdamonhangaba': 'pindamonhangaba',
}


class SheetUnavailableError(RuntimeError):
    pass


def _normalize(text: str) -> str:
    # Lowercase, no accents, trimmed (same rule as the geogrid service)
    text = unicodedata.normalize('NFKD', text)
    return text.encode('ascii', 'ignore').decode('ascii').strip().lower()


def has_info(value) -> bool:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return False
    return str(value).strip().lower() not in NO_INFO


def port_status(row) -> str:
    # Any client data (MAC, contract...) -> the port has a client
    if any(has_info(row.get(col)) for col in CLIENT_COLUMNS):
        return STATUS_CLIENT
    # No client but a technician went there -> the port is free
    if has_info(row.get('TÉCNICO')):
        return STATUS_FREE
    return STATUS_UNCHECKED


def normalize_sigla(value) -> str:
    """CTO code without the city prefix Geogrid adds.

    'DVL-CJ-207' and 'CJ-207' -> 'CJ207'; 'TV- 533' -> 'TV533';
    'CA-502 - https://maps...' -> 'CA502'. The same code can exist in more
    than one city, which is why the match also compares the city.
    """
    _, code = _split_sigla(value)
    return code


def sigla_prefix(value) -> str:
    """City prefix of the sigla: 'DVL-CJ-207' -> 'DVL'; 'CJ-207' -> ''."""
    prefix, _ = _split_sigla(value)
    return prefix


def _split_sigla(value) -> tuple[str, str]:
    if not has_info(value):
        return '', ''
    text = str(value).split(' - ')[0]
    tokens = re.findall(r'[A-Z0-9]+', _normalize(text).upper())
    prefix = ''
    # City prefix: 'DVL' in 'DVL-CJ-207' (letters followed by letters+number)
    if (
        len(tokens) >= PREFIXED_SIGLA_TOKENS
        and tokens[0].isalpha()
        and tokens[1].isalpha()
    ):
        prefix, tokens = tokens[0], tokens[1:]
    code = ''.join(tokens)
    # Without a number it is a note ("troca de caixa"), not a CTO name
    if not re.search(r'\d', code):
        return '', ''
    return prefix, code


def normalize_city(value) -> str:
    if not has_info(value):
        return ''
    city = _normalize(str(value))
    city = CITY_ALIASES.get(city, city)
    return city if re.search(r'[a-z]', city) else ''


def clean_tab(df: pd.DataFrame, name: str) -> pd.DataFrame | None:
    df = df.dropna(how='all')
    if df.empty:
        return None

    # First row is the header; it repeats on top of every CTO block
    df.columns = df.iloc[0]
    is_header = df[df.columns[0]] == df.columns[0]
    block = is_header.cumsum()
    df = df[~is_header]
    block = block[~is_header]

    df = df.loc[:, df.columns.notna()]
    df.columns = [
        RENAME_COLUMNS.get(str(c).strip(), str(c).strip()) for c in df.columns
    ]
    # A repeated name after renaming would break reindex/concat
    df = df.loc[:, ~df.columns.duplicated()]

    df = df.dropna(how='all')
    if df.empty:
        return None

    df = df.copy()
    # The CTO name/city is often typed only on the block's first rows
    for col in ('NOMENCLATURA', 'CIDADE'):
        if col in df.columns:
            df[col] = df.groupby(block[df.index])[col].transform(
                lambda s: s.ffill().bfill()
            )
    df['ABA'] = name
    return df


def _parse_date(value):
    # Dates typed as text: pt-BR "18/03*2026" (typo) or ISO "2026-03-18"
    if isinstance(value, str):
        text = value.strip().replace('*', '/')
        iso = bool(re.match(r'\d{4}-\d{1,2}-\d{1,2}', text))
        return pd.to_datetime(text, dayfirst=not iso, errors='coerce')
    return value


def build_sheet_df(tabs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    cleaned = [clean_tab(df, name) for name, df in tabs.items()]
    cleaned = [df for df in cleaned if df is not None]
    if not cleaned:
        return pd.DataFrame(columns=[*SHEET_COLUMNS, 'STATUS'])

    df = pd.concat(cleaned, ignore_index=True).reindex(columns=SHEET_COLUMNS)

    # Excel turned "3/3" into a date (2026-03-03): back to day/month text
    df['PLACA E PORTA OLT'] = df['PLACA E PORTA OLT'].map(
        lambda v: f'{v.day}/{v.month}' if hasattr(v, 'day') else v
    )
    df['DATA'] = pd.to_datetime(df['DATA'].map(_parse_date), errors='coerce')
    df['STATUS'] = df.apply(port_status, axis=1)
    return df


def load_sheet() -> pd.DataFrame:
    url = get_settings().ATENDENTES_SHEET_URL
    if not url:
        raise SheetUnavailableError('ATENDENTES_SHEET_URL is not configured')

    logger.info('Fetching attendants CTO sheet')
    try:
        response = requests.get(url, timeout=FETCH_TIMEOUT_SECONDS)
        response.raise_for_status()
        tabs = pd.read_excel(
            BytesIO(response.content),
            sheet_name=None,
            header=None,
            engine='openpyxl',
        )
    except (requests.RequestException, ValueError) as error:
        raise SheetUnavailableError(str(error)) from error

    return build_sheet_df(tabs)


def _unique(values) -> list[str]:
    seen = []
    for value in values:
        if has_info(value):
            text = str(value).strip()
            if text not in seen:
                seen.append(text)
    return seen


def _summarize_ports(ports: pd.DataFrame) -> dict:
    last_date = ports['DATA'].max()
    status = ports['STATUS'].value_counts()
    return {
        'nomenclaturas': _unique(ports['NOMENCLATURA']),
        'cidades_planilha': _unique(ports['CIDADE']),
        'abas': _unique(ports['ABA']),
        'atendentes': _unique(ports['ATENDENTE']),
        'tecnicos': _unique(ports['TÉCNICO']),
        'ultima_data': None if pd.isna(last_date) else last_date.date(),
        'portas_planilha': len(ports),
        'portas_com_cliente': int(status.get(STATUS_CLIENT, 0)),
        'portas_livres_planilha': int(status.get(STATUS_FREE, 0)),
        'portas_nao_checadas': int(status.get(STATUS_UNCHECKED, 0)),
    }


def match_critical_ctos(
    ctos: pd.DataFrame, sheet: pd.DataFrame, max_livres: int = 1
) -> dict:
    ctos = ctos.copy()
    ctos['_sigla'] = ctos['Sigla'].map(normalize_sigla)
    ctos['_cidade'] = ctos['Cidade'].map(normalize_city)

    # Prefix -> city as Geogrid uses it ('DVL' -> 'divinopolis')
    prefixes = ctos['Sigla'].map(sigla_prefix)
    prefix_city = (
        ctos
        .assign(_prefixo=prefixes)
        .loc[(prefixes != '') & (ctos['_cidade'] != '')]
        .groupby('_prefixo')['_cidade']
        .agg(lambda cities: cities.mode().iloc[0])
        .to_dict()
    )

    sheet = sheet.copy()
    sheet['_sigla'] = sheet['NOMENCLATURA'].map(normalize_sigla)
    sheet['_cidade'] = sheet['CIDADE'].map(normalize_city)
    # Blank city in the sheet: take it from the prefix ('DVL-CJ-207')
    from_prefix = sheet['NOMENCLATURA'].map(sigla_prefix).map(prefix_city)
    blank = sheet['_cidade'].eq('')
    sheet.loc[blank, '_cidade'] = from_prefix[blank].fillna('')
    sheet = sheet[sheet['_sigla'] != '']
    sheet_by_sigla = dict(tuple(sheet.groupby('_sigla')))

    # A sigla repeated in Geogrid (same name in other cities) needs the city
    # to tell the boxes apart
    sigla_count = ctos.loc[ctos['_sigla'] != '', '_sigla'].value_counts()

    livres = pd.to_numeric(ctos['Portas livres'], errors='coerce')
    critical = ctos[(livres <= max_livres) & (ctos['_sigla'] != '')]

    found = []
    for _, cto in critical.iterrows():
        ports = sheet_by_sigla.get(cto['_sigla'])
        if ports is None:
            continue
        repeated = bool(sigla_count.get(cto['_sigla'], 0) > 1)
        if repeated:
            ports = ports[ports['_cidade'] == cto['_cidade']]
            if ports.empty:
                continue

        found.append({
            'sigla': cto['Sigla'],
            'cidade': cto['Cidade'],
            'regiao': cto['Regiao'],
            'bairro': cto['Bairro'],
            'tipo': cto['Tipo'],
            'quantidade_portas': int(cto['Quantidade portas']),
            'portas_ocupadas': int(cto['Portas ocupadas']),
            'portas_livres': int(cto['Portas livres']),
            'portas_bloqueadas': int(cto['Portas bloqueadas']),
            'casou_por_cidade': repeated,
            **_summarize_ports(ports),
        })

    found.sort(key=lambda item: (item['portas_livres'], item['sigla']))
    return {
        'max_livres': max_livres,
        'total_criticas': len(critical),
        'total_encontradas': len(found),
        'ctos': found,
    }


def find_critical_ctos(max_livres: int = 1) -> dict | None:
    """None when the Geogrid viabilidade export does not exist yet."""
    ctos = get_cto_table()
    if ctos is None:
        return None
    return match_critical_ctos(ctos, load_sheet(), max_livres)
