"""
Detecção de identidades contábeis entre medições.

Caso típico: uma medição TOTAL é exatamente a soma de todas as demais
(ex.: MUX = PLASBIL + PIETROBON + ... + LIQUIDA_MUX). Nesse caso uma das
parcelas costuma ser a "líquida", calculada por diferença
(LIQUIDA_MUX = MUX - demais). Projetar todas de forma independente pode gerar
totais incoerentes; o programa detecta a identidade e oferece calcular a
medição derivada a partir das projeções das demais.

Observação: algebricamente qualquer parcela pode ser escrita como
"total - demais"; por isso a medição derivada é confirmada pelo usuário,
com sugestão automática (nome contendo LIQUID/SALDO/RESID, senão a última
coluna).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import config

_PALAVRAS_DERIVADA = ("LIQUID", "SALDO", "RESID", "DIFEREN")


@dataclass
class Total:
    base: str                # medição que é a soma das demais
    parcelas: list[str]      # demais medições (na ordem do cabeçalho)
    erro_max: float

    def descricao(self) -> str:
        return f"{self.base} = {' + '.join(self.parcelas)}"

    def sugestao_derivada(self) -> str:
        for p in self.parcelas:
            if any(k in p.upper() for k in _PALAVRAS_DERIVADA):
                return p
        return self.parcelas[-1]


@dataclass
class Identidade:
    derivada: str            # medição calculada
    base: str                # medição total
    subtraidas: list[str]    # medições subtraídas da base
    erro_max: float

    def descricao(self) -> str:
        return f"{self.derivada} = {self.base} - ({' + '.join(self.subtraidas)})"

    def calcular(self, proj: dict[str, np.ndarray]) -> np.ndarray:
        r = np.array(proj[self.base], dtype=float)
        for s in self.subtraidas:
            r = r - np.asarray(proj[s], dtype=float)
        return r


def detectar_totais(medicoes: list[str], valores: dict[str, np.ndarray]) -> list[Total]:
    """Procura medições que sejam, em todos os meses, a soma exata de todas as outras."""
    if len(medicoes) < 3:
        return []
    mat = np.column_stack([valores[m] for m in medicoes])
    if np.isnan(mat).any():
        return []
    soma = mat.sum(axis=1)
    totais = []
    for j, base in enumerate(medicoes):
        resid = mat[:, j] - (soma - mat[:, j])
        tol = config.TOL_IDENTIDADE_ABS + config.TOL_IDENTIDADE_REL * np.abs(mat[:, j])
        if np.any(mat[:, j] != 0) and np.all(np.abs(resid) <= tol):
            parcelas = [m for k, m in enumerate(medicoes) if k != j]
            totais.append(Total(base, parcelas, float(np.max(np.abs(resid)))))
    return totais


def criar_identidade(total: Total, derivada: str) -> Identidade:
    if derivada not in total.parcelas:
        raise ValueError(f"'{derivada}' não é parcela de {total.base}.")
    return Identidade(derivada, total.base, [p for p in total.parcelas if p != derivada], total.erro_max)
