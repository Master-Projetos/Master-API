import pandas as pd
import pytest

from app.modules.geogrid.critical_ctos import (
    STATUS_CLIENT,
    STATUS_FREE,
    STATUS_UNCHECKED,
    build_sheet_df,
    match_critical_ctos,
    normalize_city,
    normalize_sigla,
    port_status,
)

SHEET_PORTS = 4
DATED_PORTS = 3
CRITICAL = 2

HEADER = ['PORTA', 'MAC', 'NOME', 'DATA', 'TÉCNICO', 'NOMECLATURA', 'CIDADE']


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('TV- 533', 'TV533'),
        ('DVL-CJ-207', 'CJ207'),
        ('CJ-207', 'CJ207'),
        ('dvl-cj 207', 'CJ207'),
        ('RA 311', 'RA311'),
        ('tv-533', 'TV533'),
        (' BJ304', 'BJ304'),
        ('CA-502 - https://maps.app.goo.gl/x', 'CA502'),
        ('troca de caixa', ''),
        ('*', ''),
        ('--', ''),
        (None, ''),
    ],
)
def test_normalize_sigla(raw, expected):
    assert normalize_sigla(raw) == expected


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('SJC', 'sao jose dos campos'),
        ('S.J dos Campos', 'sao jose dos campos'),
        ('SÃO JOSÉ DOS CAMPOS', 'sao jose dos campos'),
        ('dvl', 'divinopolis'),
        ('Divinópolis', 'divinopolis'),
        ('*', ''),
        ('102241', ''),
    ],
)
def test_normalize_city(raw, expected):
    assert normalize_city(raw) == expected


@pytest.mark.parametrize(
    ('row', 'expected'),
    [
        ({'MAC': 'e0-67-b3-a6-5c-49', 'TÉCNICO': 'Lazaro'}, STATUS_CLIENT),
        ({'MAC': 'Porta vaga', 'TÉCNICO': 'Lazaro'}, STATUS_FREE),
        ({'MAC': None, 'TÉCNICO': 'Lazaro'}, STATUS_FREE),
        ({'MAC': None, 'TÉCNICO': None}, STATUS_UNCHECKED),
        ({'MAC': 'Vaga', 'TÉCNICO': '*'}, STATUS_UNCHECKED),
    ],
)
def test_port_status(row, expected):
    assert port_status(row) == expected


def _tab(rows):
    # Header repeated on top of each block, like the real sheet
    return pd.DataFrame([HEADER, *rows, [None] * len(HEADER), HEADER])


def _sheet():
    return build_sheet_df({
        'Ana': _tab([
            ['01', 'aa-bb', 'JOAO', '2026-10-01', 'Elton', 'TV- 533', 'SJC'],
            ['02', None, None, '2026-10-02', 'Elton', 'TV- 533', 'SJC'],
            ['03', None, None, None, None, 'TV- 533', 'SJC'],
        ]),
        'Bia': _tab([
            ['01', 'cc-dd', 'MARIA', '18/03*2026', 'Lazaro', 'CA-100', 'dvl'],
        ]),
        'Vazia': pd.DataFrame(),
    })


def _ctos(rows):
    columns = [
        'Sigla',
        'Cidade',
        'Regiao',
        'Bairro',
        'Tipo',
        'Quantidade portas',
        'Portas ocupadas',
        'Portas livres',
        'Portas bloqueadas',
    ]
    return pd.DataFrame(rows, columns=columns)


def test_build_sheet_df():
    sheet = _sheet()
    assert len(sheet) == SHEET_PORTS
    assert set(sheet['ABA']) == {'Ana', 'Bia'}
    assert 'NOMENCLATURA' in sheet.columns
    assert sheet['DATA'].notna().sum() == DATED_PORTS
    assert list(sheet['STATUS'][:3]) == [
        STATUS_CLIENT,
        STATUS_FREE,
        STATUS_UNCHECKED,
    ]


def test_match_unique_sigla_ignores_city():
    ctos = _ctos([
        ['TV-533', 'São José dos Campos', 'SP', 'X', 'CTO', 16, 16, 0, 0],
        ['TV-900', 'São José dos Campos', 'SP', 'X', 'CTO', 16, 15, 1, 0],
        ['CA-100', 'Itaúna', 'Centro-Oeste', 'X', 'CTO', 8, 4, 4, 0],
    ])
    result = match_critical_ctos(ctos, _sheet(), max_livres=1)

    assert result['total_criticas'] == CRITICAL
    assert result['total_encontradas'] == 1
    cto = result['ctos'][0]
    assert cto['sigla'] == 'TV-533'
    assert cto['casou_por_cidade'] is False
    assert cto['abas'] == ['Ana']
    assert cto['portas_com_cliente'] == 1
    assert cto['portas_livres_planilha'] == 1
    assert cto['portas_nao_checadas'] == 1
    assert str(cto['ultima_data']) == '2026-10-02'


def test_repeated_sigla_requires_city():
    ctos = _ctos([
        ['CA-100', 'Divinópolis', 'Centro-Oeste', 'X', 'CTO', 8, 8, 0, 0],
        ['CA-100', 'Itaúna', 'Centro-Oeste', 'X', 'CTO', 8, 8, 0, 0],
    ])
    result = match_critical_ctos(ctos, _sheet(), max_livres=1)

    assert result['total_criticas'] == CRITICAL
    assert [c['cidade'] for c in result['ctos']] == ['Divinópolis']
    assert result['ctos'][0]['casou_por_cidade'] is True


def test_max_livres_filter():
    ctos = _ctos([
        ['CA-100', 'Divinópolis', 'Centro-Oeste', 'X', 'CTO', 8, 4, 4, 0],
    ])
    assert match_critical_ctos(ctos, _sheet(), 1)['total_encontradas'] == 0
    assert match_critical_ctos(ctos, _sheet(), 4)['total_encontradas'] == 1


def test_block_name_and_city_fill_the_whole_block():
    sheet = build_sheet_df({
        'Ana': _tab([
            ['01', 'aa', 'JOAO', None, 'Elton', 'TV-533', 'SJC'],
            ['02', None, None, None, None, None, None],
        ]),
    })
    assert list(sheet['NOMENCLATURA']) == ['TV-533', 'TV-533']
    assert list(sheet['CIDADE']) == ['SJC', 'SJC']


def test_geogrid_city_prefix_matches_sheet_code_and_city():
    sheet = build_sheet_df({
        'Ana': _tab([
            ['01', 'aa', 'JOAO', None, 'Elton', 'CJ-207', 'dvl'],
            ['01', 'bb', 'ZE', None, 'Elton', 'CJ-207', 'Itaúna'],
        ]),
    })
    ctos = _ctos([
        ['DVL-CJ-207', 'Divinópolis', 'Centro-Oeste', '', 'CTO', 8, 8, 0, 0],
        ['ITA-CJ-207', 'Itaúna', 'Centro-Oeste', '', 'CTO', 8, 4, 4, 0],
    ])
    result = match_critical_ctos(ctos, sheet, max_livres=1)

    assert [c['sigla'] for c in result['ctos']] == ['DVL-CJ-207']
    cto = result['ctos'][0]
    assert cto['casou_por_cidade'] is True
    assert cto['cidades_planilha'] == ['dvl']
    assert cto['portas_planilha'] == 1


def test_blank_city_comes_from_the_sigla_prefix():
    sheet = build_sheet_df({
        'Ana': _tab([['01', 'aa', 'JOAO', None, 'Elton', 'DVL-CJ-207', None]]),
    })
    ctos = _ctos([
        ['DVL-CJ-207', 'Divinópolis', 'Centro-Oeste', '', 'CTO', 8, 8, 0, 0],
        ['SJC-CJ-207', 'São José dos Campos', 'SP', '', 'CTO', 8, 8, 0, 0],
    ])
    result = match_critical_ctos(ctos, sheet, max_livres=1)

    assert [c['sigla'] for c in result['ctos']] == ['DVL-CJ-207']
