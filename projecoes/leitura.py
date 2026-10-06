"""Leitura e validação do arquivo de dados históricos."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import numpy as np

from . import config
from .datas import formatar_data, indice_mes


class ErroLeitura(Exception):
    """Erro de formato ou consistência no arquivo de entrada."""


@dataclass
class DadosHistoricos:
    datas: list[date]
    medicoes: list[str]                      # na ordem do cabeçalho
    valores: dict[str, np.ndarray]           # nome -> array (pode conter NaN)
    avisos: list[str] = field(default_factory=list)

    @property
    def primeira_data(self) -> date:
        return self.datas[0]

    @property
    def ultima_data(self) -> date:
        return self.datas[-1]


def _converter_numero(texto: str, linha: int, coluna: str) -> float:
    s = texto.strip().replace(" ", "")
    if s == "":
        return math.nan
    if config.SEPARADOR_DECIMAL == ",":
        if "," in s:
            # vírgula = decimal; pontos (se houver) = milhar
            s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError as exc:
        raise ErroLeitura(
            f"Valor numérico inválido '{texto}' na linha {linha}, coluna '{coluna}'."
        ) from exc


def _converter_data(texto: str, linha: int) -> date:
    s = texto.strip()
    try:
        d = datetime.strptime(s, config.FORMATO_DATA).date()
    except ValueError as exc:
        raise ErroLeitura(
            f"Data inválida '{texto}' na linha {linha}. Formato esperado: DD/MM/AAAA."
        ) from exc
    return date(d.year, d.month, 1)


def ler_dados_historicos(caminho: str | Path) -> DadosHistoricos:
    caminho = Path(caminho)
    if not caminho.is_file():
        raise ErroLeitura(f"Arquivo não encontrado: {caminho}")

    with open(caminho, "r", encoding=config.ENCODING_ENTRADA, newline="") as f:
        linhas = [l for l in csv.reader(f, delimiter=config.SEPARADOR)]

    # remove linhas totalmente vazias
    linhas = [l for l in linhas if any(c.strip() for c in l)]
    if len(linhas) < 2:
        raise ErroLeitura("O arquivo não possui dados (apenas cabeçalho ou vazio).")

    cabecalho = [c.strip() for c in linhas[0]]
    # remove colunas vazias ao final (ex.: ';' sobrando)
    while cabecalho and cabecalho[-1] == "":
        cabecalho.pop()
    if len(cabecalho) < 2:
        raise ErroLeitura("O cabeçalho deve ter a coluna DATA e ao menos uma medição.")
    if cabecalho[0].upper() != config.COLUNA_DATA:
        raise ErroLeitura(
            f"A primeira coluna deve se chamar '{config.COLUNA_DATA}' (encontrado '{cabecalho[0]}')."
        )
    medicoes = cabecalho[1:]
    if any(m == "" for m in medicoes):
        raise ErroLeitura("Há medição com nome vazio no cabeçalho.")
    duplicadas = sorted({m for m in medicoes if medicoes.count(m) > 1})
    if duplicadas:
        raise ErroLeitura(f"Nomes de medição duplicados no cabeçalho: {', '.join(duplicadas)}")

    datas: list[date] = []
    matriz: list[list[float]] = []
    avisos: list[str] = []
    for n_linha, linha in enumerate(linhas[1:], start=2):
        celulas = list(linha) + [""] * (len(cabecalho) - len(linha))
        extras = [c for c in celulas[len(cabecalho):] if c.strip()]
        if extras:
            raise ErroLeitura(f"Linha {n_linha} possui mais colunas que o cabeçalho.")
        datas.append(_converter_data(celulas[0], n_linha))
        matriz.append([
            _converter_numero(celulas[j + 1], n_linha, medicoes[j]) for j in range(len(medicoes))
        ])

    # ordena por data e verifica continuidade mensal
    ordem = sorted(range(len(datas)), key=lambda i: datas[i])
    if ordem != list(range(len(datas))):
        avisos.append("As linhas não estavam em ordem cronológica e foram ordenadas.")
    datas = [datas[i] for i in ordem]
    matriz = [matriz[i] for i in ordem]

    for a, b in zip(datas, datas[1:]):
        if a == b:
            raise ErroLeitura(f"Data duplicada no arquivo: {formatar_data(a)}")
        if indice_mes(b) - indice_mes(a) != 1:
            raise ErroLeitura(
                f"Falha na sequência mensal: de {formatar_data(a)} salta para {formatar_data(b)}. "
                "O histórico deve ser contínuo mês a mês."
            )

    arr = np.array(matriz, dtype=float)
    valores = {m: arr[:, j].copy() for j, m in enumerate(medicoes)}
    for m in medicoes:
        n_nan = int(np.isnan(valores[m]).sum())
        if n_nan:
            avisos.append(f"Medição '{m}': {n_nan} célula(s) vazia(s) tratada(s) como dado ausente.")

    return DadosHistoricos(datas=datas, medicoes=medicoes, valores=valores, avisos=avisos)
