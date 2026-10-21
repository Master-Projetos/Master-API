from app.core.settings import get_settings

settings = get_settings()

ALLOWED_RELATORIES = [
    'cabos',
    'dutos',
    'poste',
    'estacao',
    'pontoaccesso',
    'grupoaccesso',
    'caixa',
    'terminal',
    'rack',
    'reserva',
    'viabilidade',
    'interesse',
    'equipamento',
    'antenas',
]

# Only these realtory types expose a "Tipo" field in the form
ALLOWED_ITEM_TYPES = ['viabilidade', 'terminal', 'caixa', 'rack']

GEOGRID_URL = 'https://morfeu.geogridmaps.com.br/rbc/'

B2B_SHEET_URL = settings.B2B_SHEET_URL

STOCK_SHEET_URL = settings.STOCK_SHEET_URL

# SWAP_SHEET_URL = settings.SWAP_SHEET_URL

SWAP_V5_SHEET_URL = settings.SWAP_V5_SHEET_URL

# Base export URL of the v6 stock sheet, without the tab (gid)
STOCK_V6_SHEET_URL = settings.STOCK_V6_SHEET_URL

# Tab name in the response -> gid of the tab in the sheet
STOCK_V6_SHEETS = {
    'dvl': '1702172882',
    'lav': '1278376259',
    'tte': '1643373498',
    'uni': '749566893',
    'mcl': '764963849',
}

STOCK_V6_DELETE_COLUMNS = [
    'Tipo Saldo',
    'Grupo',
    'Codmat',
    'Descrição Auxiliar',
    'Codcpl',
    'Cód. Mat. Auxiliar',
    'Cód. Cpl. Auxiliar',
    'Prog. RM',
    'Prog. TM',
    'Saldo Disponível',
    'Valor',
    'Cod. Grupo Material',
    'Grupo de Material',
]

MINIMAL_STOCK_DELETE = [
    'Unid.',
    'Saldo CD',
    'REPOSIÇÃO REGIONAL',
    'SALDO LAVRAS',
    'REPOSIÇÃO REGIONAL.1',
    'SALDO TAUBATE',
    'REPOSIÇÃO REGIONAL.2',
    'SALDO UNAI',
    'REPOSIÇÃO REGIONAL.3',
    'SALDO MONTES CLAROS',
    'REPOSIÇÃO REGIONAL.4',
    'TOTAL',
]

# Swap sheet sections the API can return; all of them when none is asked for
SWAP_SECTIONS = [
    'colocation',
    'dark-fiber',
    'trunk',
    'transport',
    'to-define',
    'lambdas',
    'capacity',
    'lan-to-lan',
    'last_mille',
    'switch_port',
    'link_ip',
]

# Cities without a listed region fall back to "Sul".
REGION_CITIES = {
    'Centro-Oeste': [
        'divinopolis',
        'belo horizonte',
        'betim',
        'carmo do cajuru',
        'conselheiro lafaiete',
        'itauna',
        'juatuba',
        'mateus leme',
        'nova serrana',
        'para de minas',
        'pitangui',
        'santo antonio dos campos',
        'sao sebastiao do oeste',
        'são jose dos campos',
        'sete lagoas',
    ],
    'SP': [
        'cacapava',
        'campos do jordao',
        'guaratingueta',
        'lorena',
        'pindamonhangaba',
        'sao jose dos campos',
        'taubate',
        'tremembe',
    ],
    'Norte': [
        'montes claros',
        'paracatu',
        'unai',
    ],
    'Sul': [
        'delfim moreira',
        'itajuba',
        'lavras',
        'passos',
        'pirangucu',
        'piranguinho',
        'pocos de caldas',
        'pouso alegre',
        'santa rita do sapucai',
        'sao sebastiao do paraiso',
        'tres coracoes',
        'varginha',
    ],
}

# OneDrive download link of the v7 pole licensing workbook
POLES_V7_SHEET_URL = settings.POLES_V7_SHEET_URL

# One tab per utility company, each with a "CIDADES" table
POLES_V7_UTILITY_SHEETS = ['CEMIG', 'DME', 'EDP', 'ELEKTRO']
