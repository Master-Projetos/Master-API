"""Gera as bases de postes da DME, EDP SP e Elektro a partir da BDGD (ANEEL).

A base da Cemig-D vem pronta do GitHub VinnyByn/ROUTE-MAP; as das outras
distribuidoras saem deste script, no mesmo formato (tiles Web Mercator de zoom
13, 4 bytes por poste), e vão para o release EXTRA_RELEASE do Master-API, de
onde a API baixa (ver app/modules/route_poles/analysis/pole_base.py).

Uso, da raiz do projeto (precisa do pyogrio: poetry install --with postes):
  python -m scripts.gerar_base_postes                  (as três distribuidoras)
  python -m scripts.gerar_base_postes edp-sp elektro
  python -m scripts.gerar_base_postes dme --gdb Dmed_51_2025-12-31.gdb.zip

Para cada distribuidora: acha a BDGD mais nova no portal de dados abertos da
ANEEL, baixa o File Geodatabase (centenas de MB, fica em cache), lê os postes
(camada PONNOT, TIP_PN = 'POS') e grava <saida>/postes-<distribuidora>.tar.gz.
"""

import argparse
import datetime as dt
import io
import json
import os
import re
import struct
import sys
import tarfile
import tempfile
import urllib.parse
import zipfile
from pathlib import Path

import numpy as np
import pyogrio

from app.modules.route_poles.analysis.http import download, fetch
from app.modules.route_poles.analysis.pole_base import (
    EXTRA_RELEASE,
    POLE_BASES,
    TILE_N,
    TILE_STEPS,
    TILE_ZOOM,
)

URL_BUSCA_ANEEL = (
    'https://dadosabertos-aneel.opendata.arcgis.com/api/search/v1'
    '/collections/all/items?q={q}&limit=100'
)
URL_ARQUIVO_ANEEL = (
    'https://www.arcgis.com/sharing/rest/content/items/{id}/data'
)

# arquivo -> (busca no portal, regex do título). Os títulos mudam de nome com
# o tempo (ELEKTRO_385 / Neoenergia_Elektro_385, DMED_51 / Dmed_51) e a
# EDP_ES_380 (Espírito Santo) não pode entrar
BUSCAS = {
    'postes-dme.tar.gz': ('Dmed', r'^dmed_51_'),
    'postes-edp-sp.tar.gz': ('EDP_SP', r'^edp_sp_391_'),
    'postes-elektro.tar.gz': ('Elektro', r'^(neoenergia_)?elektro_385_'),
}
# slug da linha de comando -> (distribuidora, arquivo), na ordem de
# POLE_BASES
DISTRIBUIDORAS = {
    base.asset.removeprefix('postes-').removesuffix('.tar.gz'): (
        base.utility,
        base.asset,
    )
    for base in POLE_BASES
    if base.asset in BUSCAS
}

CAMADA_POSTES = 'PONNOT'
FILTRO_POSTES = "TIP_PN = 'POS'"
DATA_TITULO = re.compile(r'\d{4}-\d{2}-\d{2}')
# Ponto WKB: ordem dos bytes (1) + tipo (4) + x, y (8 + 8)
WKB_PONTO_BYTES = 21
# Limites do Web Mercator
MAX_LON, MAX_LAT = 180, 85
# Geográficas: SIRGAS 2000 (a da BDGD) ou WGS 84, que diferem em centímetros
CRS_ACEITOS = {'EPSG:4674', 'EPSG:4326'}


def log(*partes):
    print(*partes, file=sys.stderr, flush=True)


def buscar_bdgd(busca, regex):
    """A BDGD mais nova do portal da ANEEL: {id, titulo, data_base}."""
    url = URL_BUSCA_ANEEL.format(q=urllib.parse.quote(busca))
    itens = json.loads(fetch(url))['features']
    candidatos = []
    for item in itens:
        p = item.get('properties') or {}
        titulo = p.get('title') or ''
        data = DATA_TITULO.search(titulo)
        if (
            p.get('type') == 'File Geodatabase'
            and re.match(regex, titulo, re.IGNORECASE)
            and data
        ):
            candidatos.append((data.group(), p.get('modified') or 0, item))
    if not candidatos:
        raise SystemExit(f'Nenhuma BDGD "{busca}" no portal da ANEEL.')
    data, _, item = max(candidatos, key=lambda c: c[:2])
    return {
        'id': item['id'],
        'titulo': item['properties']['title'],
        'data_base': data,
    }


def baixar_gdb(bdgd, pasta_cache):
    os.makedirs(pasta_cache, exist_ok=True)
    destino = os.path.join(pasta_cache, f'{bdgd["titulo"]}.gdb.zip')
    if not os.path.exists(destino):
        log(f'  Baixando {bdgd["titulo"]}...')
        download(
            URL_ARQUIVO_ANEEL.format(id=bdgd['id']),
            Path(destino),
            timeout=3600,
        )
    return destino


def ler_postes_gdb(caminho_zip):
    """(lon, lat) dos postes do File Geodatabase zipado, em arrays numpy."""
    with zipfile.ZipFile(caminho_zip) as z:
        pastas = {
            n.split('.gdb/')[0] + '.gdb' for n in z.namelist() if '.gdb/' in n
        }
    if len(pastas) != 1:
        raise SystemExit(
            f'{caminho_zip}: esperava uma pasta .gdb, achei {len(pastas)}.'
        )
    caminho = (
        f'/vsizip/{os.path.abspath(caminho_zip).replace(os.sep, "/")}'
        f'/{pastas.pop()}'
    )
    meta, _, geometrias, _ = pyogrio.raw.read(
        caminho,
        layer=CAMADA_POSTES,
        columns=['TIP_PN'],
        where=FILTRO_POSTES,
    )
    crs = meta.get('crs')
    if crs not in CRS_ACEITOS:
        raise SystemExit(
            f'{caminho_zip}: coordenadas em {crs}, esperava {CRS_ACEITOS}.'
        )

    lon = np.empty(len(geometrias))
    lat = np.empty(len(geometrias))
    for i, wkb in enumerate(geometrias):
        lon[i], lat[i] = ponto_wkb(wkb)
    return lon, lat


def ponto_wkb(wkb):
    """(x, y) de um ponto WKB/ISO WKB (2D, Z ou M); NaN sem geometria."""
    if wkb is None or len(wkb) < WKB_PONTO_BYTES:
        return float('nan'), float('nan')
    ordem = '<' if wkb[0] == 1 else '>'
    (tipo,) = struct.unpack_from(f'{ordem}I', wkb, 1)
    # ISO (1001, 2001, 3001) e EWKB (bits altos) também são pontos
    if (tipo & 0xFFFF) % 1000 != 1:
        return float('nan'), float('nan')
    return struct.unpack_from(f'{ordem}dd', wkb, 5)


def tiles(lon, lat):
    """Gera (tx, ty, bytes) por tile não vazio: Uint16 LE x, y por poste."""
    validos = (
        np.isfinite(lon)
        & np.isfinite(lat)
        & (np.abs(lon) <= MAX_LON)
        & (np.abs(lat) <= MAX_LAT)
    )
    lon, lat = lon[validos], lat[validos]
    # Mesmas contas de pole_base.lon_to_tile_x / lat_to_tile_y, vetorizadas
    fx = (lon + 180) / 360 * TILE_N
    rad = np.radians(lat)
    fy = (1 - np.log(np.tan(rad) + 1 / np.cos(rad)) / np.pi) / 2 * TILE_N
    tx, ty = np.floor(fx).astype(np.int64), np.floor(fy).astype(np.int64)
    qx = np.minimum(np.floor((fx - tx) * TILE_STEPS), TILE_STEPS - 1)
    qy = np.minimum(np.floor((fy - ty) * TILE_STEPS), TILE_STEPS - 1)
    pares = np.column_stack((qx, qy)).astype('<u2')

    chave = tx * TILE_N + ty
    ordem = np.argsort(chave, kind='stable')
    chaves, inicios = np.unique(chave[ordem], return_index=True)
    for k, ini, fim in zip(chaves, inicios, [*inicios[1:], len(ordem)]):
        yield int(k // TILE_N), int(k % TILE_N), pares[ordem[ini:fim]]


def gravar_base(destino, distribuidora, bdgd, lon, lat):
    versao = 'v-' + bdgd['data_base']
    total = n_tiles = 0
    with tarfile.open(destino + '.part', 'w:gz') as tar:
        for tx, ty, pares in tiles(lon, lat):
            adicionar(tar, f'{versao}/{tx}/{ty}.bin', pares.tobytes())
            total += len(pares)
            n_tiles += 1
        manifest = {
            'fonte': 'BDGD/ANEEL',
            'distribuidora': distribuidora,
            'arquivo': bdgd['titulo'],
            'data_base': bdgd['data_base'],
            'versao': versao,
            'gerado_em': dt.datetime.now(dt.UTC).isoformat(timespec='seconds'),
            'total': total,
            'tiles': n_tiles,
            'zoom': TILE_ZOOM,
        }
        adicionar(
            tar,
            'manifest.json',
            json.dumps(manifest, ensure_ascii=False, indent=2).encode(),
        )
    os.replace(destino + '.part', destino)
    return manifest


def adicionar(tar, nome, dados):
    info = tarfile.TarInfo(nome)
    info.size = len(dados)
    tar.addfile(info, io.BytesIO(dados))


def main():
    ap = argparse.ArgumentParser(
        description='Gera as bases de postes das distribuidoras a partir da '
        'BDGD da ANEEL.'
    )
    ap.add_argument(
        'distribuidoras',
        nargs='*',
        help=f'Padrão: todas ({", ".join(DISTRIBUIDORAS)})',
    )
    ap.add_argument(
        '--saida', default='build_postes', help='Pasta dos .tar.gz gerados'
    )
    ap.add_argument(
        '--cache',
        default=os.path.join(tempfile.gettempdir(), 'cache_bdgd'),
        help='Pasta onde ficam os .gdb.zip baixados da ANEEL',
    )
    ap.add_argument(
        '--gdb',
        help='.gdb.zip já baixado (uso offline; só com uma distribuidora)',
    )
    args = ap.parse_args()
    slugs = args.distribuidoras or list(DISTRIBUIDORAS)
    desconhecidas = set(slugs) - set(DISTRIBUIDORAS)
    if desconhecidas:
        ap.error(
            f'distribuidora inválida: {", ".join(sorted(desconhecidas))} '
            f'(opções: {", ".join(DISTRIBUIDORAS)})'
        )
    if args.gdb and len(slugs) != 1:
        ap.error('--gdb precisa de exatamente uma distribuidora')

    os.makedirs(args.saida, exist_ok=True)
    for slug in slugs:
        distribuidora, arquivo = DISTRIBUIDORAS[slug]
        log(f'\n== {distribuidora}')
        if args.gdb:
            titulo = os.path.basename(args.gdb).removesuffix('.gdb.zip')
            data = DATA_TITULO.search(titulo)
            if not data:
                ap.error(f'{titulo}: sem data AAAA-MM-DD no nome do arquivo')
            bdgd = {'id': None, 'titulo': titulo, 'data_base': data.group()}
            caminho_zip = args.gdb
        else:
            bdgd = buscar_bdgd(*BUSCAS[arquivo])
            log(f'  BDGD mais nova: {bdgd["titulo"]}')
            caminho_zip = baixar_gdb(bdgd, args.cache)

        lon, lat = ler_postes_gdb(caminho_zip)
        destino = os.path.join(args.saida, arquivo)
        manifest = gravar_base(destino, distribuidora, bdgd, lon, lat)
        log(
            f'  {manifest["total"]} postes em {manifest["tiles"]} tiles '
            f'-> {destino} ({os.path.getsize(destino) / 1e6:.1f} MB)'
        )

    log(
        f'\nPublique os arquivos de {args.saida} no release '
        f'{EXTRA_RELEASE} (ver docs/v8-route-poles.md).'
    )


if __name__ == '__main__':
    main()
