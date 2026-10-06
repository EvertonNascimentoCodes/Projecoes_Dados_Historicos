"""Gravação dos arquivos CSV de resultado (mesmo padrão do arquivo de entrada)."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import numpy as np

from . import config
from .datas import formatar_data


def formatar_numero(v: float) -> str:
    casas = config.CASAS_DECIMAIS
    v = round(float(v), casas)
    if v == 0:
        v = 0.0   # evita "-0,0000"
    return f"{v:.{casas}f}".replace(".", config.SEPARADOR_DECIMAL)


def arredondar(v: np.ndarray) -> np.ndarray:
    r = np.round(np.asarray(v, dtype=float), config.CASAS_DECIMAIS)
    r[r == 0] = 0.0
    return r


def _gravar(caminho: Path, linhas: list[list[str]]) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding=config.ENCODING_SAIDA, newline="") as f:
        for l in linhas:
            f.write(config.SEPARADOR.join(l) + "\r\n")
    return caminho


def totais_anuais(datas: list[date], valores: np.ndarray) -> tuple[list[int], np.ndarray]:
    """Soma por ano dos valores mensais JÁ arredondados (fecha com o arquivo mensal)."""
    anos = sorted({d.year for d in datas})
    v = arredondar(valores)
    tot = np.array([v[[i for i, d in enumerate(datas) if d.year == a]].sum() for a in anos])
    return anos, arredondar(tot)


def gravar_resultados(pasta: Path, datas: list[date], medicoes: list[str],
                      proj: dict[str, np.ndarray]) -> list[Path]:
    """Grava os 4 arquivos principais. `proj[m]` deve ter len(datas) valores."""
    sep_cab = [config.COLUNA_DATA] + medicoes
    mat = {m: arredondar(proj[m]) for m in medicoes}
    arquivos = []

    # 1) mensal (mesmo layout do histórico)
    linhas = [sep_cab]
    for i, d in enumerate(datas):
        linhas.append([formatar_data(d)] + [formatar_numero(mat[m][i]) for m in medicoes])
    arquivos.append(_gravar(pasta / config.ARQ_MENSAL, linhas))

    # 2) anual (uma linha por ano)
    anuais = {m: totais_anuais(datas, mat[m]) for m in medicoes}
    anos = anuais[medicoes[0]][0] if medicoes else []
    linhas = [[config.COLUNA_ANO] + medicoes]
    for k, a in enumerate(anos):
        linhas.append([str(a)] + [formatar_numero(anuais[m][1][k]) for m in medicoes])
    arquivos.append(_gravar(pasta / config.ARQ_ANUAL, linhas))

    # 3) transposto mensal (medições nas linhas)
    linhas = [[config.COLUNA_MEDICAO] + [formatar_data(d) for d in datas]]
    for m in medicoes:
        linhas.append([m] + [formatar_numero(x) for x in mat[m]])
    arquivos.append(_gravar(pasta / config.ARQ_LINHAS, linhas))

    # 4) transposto anual
    linhas = [[config.COLUNA_MEDICAO] + [str(a) for a in anos]]
    for m in medicoes:
        linhas.append([m] + [formatar_numero(x) for x in anuais[m][1]])
    arquivos.append(_gravar(pasta / config.ARQ_LINHAS_ANOS, linhas))
    return arquivos


def _nome_arquivo_seguro(texto: str) -> str:
    return re.sub(r'[<>:"/\\|?*\s]+', "_", texto).strip("_")


def gravar_metodologias(pasta: Path, datas: list[date],
                        series: list[tuple[str, str, np.ndarray]]) -> list[Path]:
    """series: lista de (medicao, metodologia, valores). Um arquivo por par."""
    destino = pasta / config.PASTA_METODOLOGIAS
    destino.mkdir(parents=True, exist_ok=True)
    # remove apenas resultados de execuções anteriores deste programa
    for antigo in destino.glob("*_result.csv"):
        antigo.unlink()
    arquivos = []
    for medicao, metodo, valores in series:
        v = arredondar(valores)
        linhas = [[config.COLUNA_DATA, medicao]]
        linhas += [[formatar_data(d), formatar_numero(x)] for d, x in zip(datas, v)]
        nome = f"{_nome_arquivo_seguro(medicao)}_{_nome_arquivo_seguro(metodo)}_result.csv"
        arquivos.append(_gravar(destino / nome, linhas))
    return arquivos
