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

NUMERIC_COLUMNS = ['Valores Projetos - Aprovados', 'Valores Projetos - Total']

# Emojis, símbolos e seletores de variação (ex.: "🔴 Atrasado", "⚠️ Vence")
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


def load_b2b_data() -> pd.DataFrame:
    logger.info('Fetching B2B spreadsheet')
    df = pd.read_csv(B2B_SHEET_URL)

    df = df.drop(COLUMNS_TO_DROP, axis='columns')

    for col in NUMERIC_COLUMNS:
        df[col] = df[col].apply(parse_brl)

    df.loc[df['Status da Demanda'] == 'Concluída', 'Prazo'] = 'Concluido'

    return df


# Prioridade dos Projetos
def get_priority_counts(df: pd.DataFrame) -> dict:
    priority_counts = df['Prioridade'].value_counts()

    return priority_counts.to_dict()


# Status B2B
def get_status_counts(df: pd.DataFrame) -> dict:
    status_counts = df['Status'].value_counts()

    return status_counts.to_dict()


# Total Valores
def get_financial_summary(df: pd.DataFrame) -> dict:
    total_value = round(df['Valores Projetos - Total'].sum().item(), 2)
    average_value = round(df['Valores Projetos - Total'].mean().item(), 2)
    highest_value = round(df['Valores Projetos - Total'].max().item(), 2)
    lowest_value = round(df['Valores Projetos - Total'].min().item(), 2)
    approved_value = round(df['Valores Projetos - Aprovados'].sum().item(), 2)

    return {
        'total_value': total_value,
        'average_value': average_value,
        'highest_value': highest_value,
        'lowest_value': lowest_value,
        'approved_value': approved_value,
    }


# Status por região
def get_status_by_region(df: pd.DataFrame) -> dict:
    status_by_region = pd.crosstab(df['Região'], df['Status da Demanda'])

    return status_by_region.to_dict()


# Quantitativo x Prioridade
def get_priority_by_requester(df: pd.DataFrame) -> dict:
    priority_by_requester = pd.crosstab(df['Solicitante'], df['Prioridade'])

    return priority_by_requester.to_dict()


# Projetos por mes
def get_projects_by_month(df: pd.DataFrame) -> dict:
    start_dates = pd.to_datetime(df['Data Início'], format='%d/%m/%Y')
    projects_by_month = (
        start_dates.dt.to_period('M').value_counts().sort_index()
    )
    projects_by_month.index = projects_by_month.index.astype(str)

    return projects_by_month.to_dict()


# Situação do prazo
def get_deadline_counts(df: pd.DataFrame) -> dict:
    deadline = df['Prazo'].str.replace(EMOJI_PATTERN, '', regex=True)
    deadline_counts = deadline.str.strip().value_counts()

    return deadline_counts.to_dict()


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
