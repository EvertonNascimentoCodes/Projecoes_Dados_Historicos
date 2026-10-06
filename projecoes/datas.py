"""Utilitários de datas mensais (sempre o 1º dia do mês)."""

from __future__ import annotations

import re
from datetime import date


def indice_mes(d: date) -> int:
    """Converte uma data em um índice inteiro de meses (ano*12 + mês-1)."""
    return d.year * 12 + (d.month - 1)


def data_do_indice(i: int) -> date:
    return date(i // 12, i % 12 + 1, 1)


def somar_meses(d: date, n: int) -> date:
    return data_do_indice(indice_mes(d) + n)


def meses_entre(inicio: date, fim: date) -> int:
    """Quantidade de meses de `inicio` até `fim` (fim - inicio)."""
    return indice_mes(fim) - indice_mes(inicio)


def sequencia_mensal(inicio: date, fim: date) -> list[date]:
    """Lista de datas mensais de `inicio` até `fim`, inclusive."""
    return [data_do_indice(i) for i in range(indice_mes(inicio), indice_mes(fim) + 1)]


def formatar_data(d: date) -> str:
    return f"{d.day:02d}/{d.month:02d}/{d.year:04d}"


def formatar_mes_ano(d: date) -> str:
    return f"{d.month:02d}/{d.year:04d}"


_RE_MES_ANO = re.compile(r"^\s*(\d{1,2})\s*[/\-.]\s*(\d{4})\s*$")
_RE_DIA_MES_ANO = re.compile(r"^\s*(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{4})\s*$")


def interpretar_mes_ano(texto: str) -> date:
    """Aceita 'MM/AAAA', 'M/AAAA', 'MM-AAAA' ou 'DD/MM/AAAA'. Retorna o 1º dia do mês."""
    m = _RE_MES_ANO.match(texto)
    if m:
        mes, ano = int(m.group(1)), int(m.group(2))
    else:
        m = _RE_DIA_MES_ANO.match(texto)
        if not m:
            raise ValueError(f"Formato inválido: '{texto}'. Use MM/AAAA (ex.: 10/2026).")
        mes, ano = int(m.group(2)), int(m.group(3))
    if not 1 <= mes <= 12:
        raise ValueError(f"Mês inválido: {mes}. Deve estar entre 1 e 12.")
    if not 1900 <= ano <= 2200:
        raise ValueError(f"Ano inválido: {ano}.")
    return date(ano, mes, 1)
