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
