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