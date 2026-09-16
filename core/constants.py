ALLOWED_RELATORIES = [
    "cabos", "dutos", "poste",
    "estacao", "pontoAcesso", "grupoAcesso",
    "caixa", "terminal", "rack",
    "reserva", "viabilidade", "interesse",
    "equipamento", "antenas"
]

# Only these realtory types expose a "Tipo" field in the form
ALLOWED_ITEM_TYPES = ["viabilidade", "terminal", "caixa", "rack"]

GEOGRID_URL = "https://morfeu.geogridmaps.com.br/rbc/"

# Cities without a listed region fall back to "Sul".
REGION_CITIES = {
    "Centro-Oeste": [
        "divinopolis", "belo horizonte", "betim", "carmo do cajuru",
        "conselheiro lafaiete", "itauna", "juatuba", "mateus leme",
        "nova serrana", "para de minas", "pitangui", "santo antonio dos campos",
        "sao sebastiao do oeste", "sete lagoas",
    ],
    "SP": [
        "cacapava", "campos do jordao", "guaratingueta", "lorena",
        "pindamonhangaba", "sao jose dos campos", "taubate", "tremembe",
    ],
    "Norte": [
        "montes claros", "paracatu", "unai",
    ],
    "Sul": [
        "delfim moreira", "itajuba", "lavras", "passos", "pirangucu",
        "piranguinho", "pocos de caldas", "pouso alegre", "santa rita do sapucai",
        "sao sebastiao do paraiso", "tres coracoes", "varginha",
    ],
}