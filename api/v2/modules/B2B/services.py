import logging

import pandas as pd

from core.constants import B2B_SHEET_URL

logger = logging.getLogger(__name__)

COLUMNS_TO_DROP = [
    'Anal. Pré-Venda',
    'Anal. Projeto',
    'Vistoria',
    'Lev. de Custo',
    'Aprov. BP',
    'Projeto',
    'Estoque',
    'Operação',
    'Configuração',
    'Status ',
]

# Sheet header of the project progress (note the trailing space), derived
# from the stage checkboxes: "Não iniciado", "11% CONCLUÍDO", ..., "Concluído"


# A project with no stage checkbox filled in has not started yet
NOT_STARTED_STATUS = 'Não iniciado'

NUMERIC_COLUMNS = ['Valores Projetos - Aprovados', 'Valores Projetos - Total']

# Sheet columns exposed with each item, mapped to their response name
ITEM_COLUMNS = {
    'Prazo': 'deadline',
    'Cliente B2B': 'client',
    'Solicitante': 'requester',
    'Prioridade': 'priority',
    'Região': 'region',
    'Data Início': 'start_date',
    'Data Término': 'end_date',
    'Dias Restantes': 'remaining_days',
    'Setor Responsavel': 'sector',
}

DATE_COLUMNS = ['Data Início', 'Data Término']

TEXT_ITEM_COLUMNS = ('client', 'requester', 'priority', 'region', 'sector')

UNASSIGNED_REQUESTER = 'Sem solicitante'

# Emojis, symbols and variation selectors (e.g. "🔴 Atrasado", "⚠️ Vence")
EMOJI_PATTERN = (
    r'[\U0001F000-\U0001FAFF⌀-⏿☀-➿⬀-⯿'
    r'️‍]'
)


def parse_brl(value: str) -> float:
    value = str(value).replace('R$', '').strip()

    if not value or value.lower() == 'nan':
        return float('nan')

    # Formato BR: "1.234,56" -> ponto é milhar, vírgula é decimal
    if ',' in value:
        value = value.replace('.', '').replace(',', '.')

    return float(value)


def _build_items(df: pd.DataFrame, group: pd.Series, name: str) -> list[dict]:
    """Rows of ITEM_COLUMNS labelled by `group`, skipping empty groups."""
    items = df[list(ITEM_COLUMNS)].copy()
    items = items.rename(columns=ITEM_COLUMNS)
    items = items.drop(columns=name, errors='ignore')
    items.insert(0, name, group)
    items = items[items[name].notna()]

    for col in TEXT_ITEM_COLUMNS:
        items[col] = items[col].str.strip()

    records = items.to_dict(orient='records')
    for record in records:
        days = record['remaining_days']
        record['remaining_days'] = None if pd.isna(days) else int(days)

        for key, value in record.items():
            # NaN is not valid JSON, so an empty cell becomes null
            if pd.isna(value):
                record[key] = None
            elif isinstance(value, pd.Timestamp):
                record[key] = value.date().isoformat()

    return records


def _value_items(df: pd.DataFrame, column: str) -> list[dict]:
    """Rows holding a value in `column`, largest value first."""
    records = _build_items(df, df[column], 'value')
    for record in records:
        record['value'] = round(float(record['value']), 2)

    return sorted(records, key=lambda record: record['value'], reverse=True)


def load_b2b_data() -> pd.DataFrame:
    logger.info('Fetching B2B spreadsheet')
    df = pd.read_csv(B2B_SHEET_URL)

    df = df.drop(COLUMNS_TO_DROP, axis='columns')

    for col in NUMERIC_COLUMNS:
        df[col] = df[col].apply(parse_brl)

    df['Prazo'] = (
        df['Prazo'].str.replace(EMOJI_PATTERN, '', regex=True).str.strip()
    )

    for col in DATE_COLUMNS:
        # A date the sheet cannot parse becomes NaT, and later null
        df[col] = pd.to_datetime(df[col], format='%d/%m/%Y', errors='coerce')

    # crosstab drops rows whose key is null, so they get an explicit label
    df['Solicitante'] = df['Solicitante'].fillna(UNASSIGNED_REQUESTER)

    # A finished demand counts as "Concluido" whatever its deadline says,
    # matching status spelling variants ("Concluída", "concluida ", ...)
    demand_status = (
        df['Status da Demanda']
        .str.normalize('NFKD')
        .str.encode('ascii', 'ignore')
        .str.decode('ascii')
        .str.strip()
        .str.lower()
    )
    finished = demand_status.str.startswith('conclu', na=False)

    # The sheet may also write the deadline itself as "Concluído"
    deadline = df['Prazo'].str.normalize('NFKD').str.lower()
    finished |= deadline.str.startswith('conclu', na=False)

    df.loc[finished, 'Prazo'] = 'Concluido'

    return df


# Prioridade dos Projetos
def get_priority_counts(df: pd.DataFrame) -> dict:
    priority_counts = df['Prioridade'].value_counts()

    return priority_counts.to_dict()


# Status B2B
def get_status_counts(df: pd.DataFrame) -> dict:
    status = df['Status'].str.strip()

    return {
        'counts': status.value_counts().to_dict(),
        'items': _build_items(df, status, 'status'),
    }


# Total Valores
def get_financial_summary(df: pd.DataFrame) -> dict:
    total_value = round(df['Valores Projetos - Total'].sum().item(), 2)
    average_value = round(df['Valores Projetos - Total'].mean().item(), 2)
    highest_value = round(df['Valores Projetos - Total'].max().item(), 2)
    lowest_value = round(df['Valores Projetos - Total'].min().item(), 2)
    approved_value = round(df['Valores Projetos - Aprovados'].sum().item(), 2)

    projects = _value_items(df, 'Valores Projetos - Total')
    approved_projects = _value_items(df, 'Valores Projetos - Aprovados')

    # A project with no approved value is still waiting for approval
    unapproved = df[df['Valores Projetos - Aprovados'].isna()]
    unapproved_projects = _value_items(unapproved, 'Valores Projetos - Total')

    return {
        'total_value': total_value,
        'average_value': average_value,
        'highest_value': highest_value,
        'lowest_value': lowest_value,
        'approved_value': approved_value,
        'highest_project': projects[0] if projects else None,
        'highest_approved_project': (
            approved_projects[0] if approved_projects else None
        ),
        'approved_projects': approved_projects,
        'unapproved_projects': unapproved_projects,
    }


# Status por região
def get_status_by_region(df: pd.DataFrame) -> dict:
    demand_status = df['Status da Demanda'].str.strip()
    status_by_region = pd.crosstab(df['Região'], demand_status)

    return {
        'counts': status_by_region.to_dict(),
        'items': _build_items(df, demand_status, 'status'),
    }


# Quantitativo x Prioridade
def get_priority_by_requester(df: pd.DataFrame) -> dict:
    priority = df['Prioridade'].str.strip()
    priority_by_requester = pd.crosstab(df['Solicitante'], priority)

    return {
        'counts': priority_by_requester.to_dict(),
        'items': _build_items(df, priority, 'priority'),
    }


# Projetos por mes
def get_projects_by_month(df: pd.DataFrame) -> dict:
    start_dates = df['Data Início']
    months = start_dates.dt.to_period('M').astype(str)
    months = months.where(start_dates.notna())

    projects_by_month = months.value_counts().sort_index()

    return {
        'counts': projects_by_month.to_dict(),
        'items': _build_items(df, months, 'month'),
    }


# Situação do prazo
def get_deadline_counts(df: pd.DataFrame) -> dict:
    deadline = df['Prazo']

    return {
        'counts': deadline.value_counts().to_dict(),
        'items': _build_items(df, deadline, 'deadline'),
    }


# Consolidado para a API
def get_dashboard(df: pd.DataFrame) -> dict:
    return {
        'priority': get_priority_counts(df),
        'status': get_status_counts(df),
        'financial': get_financial_summary(df),
        'status_by_region': get_status_by_region(df),
        'priority_by_requester': get_priority_by_requester(df),
        'projects_by_month': get_projects_by_month(df),
        'deadline': get_deadline_counts(df),
    }
