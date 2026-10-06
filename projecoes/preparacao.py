"""
Preparação de cada série: identifica o período em que a unidade consumidora
está efetivamente ligada.

Regras (documentadas também no relatório):
  1. Zeros no início da série  -> unidade ainda não ligada (descartados).
  2. Blocos internos com >= MIN_ZEROS_CONSECUTIVOS zeros seguidos -> unidade
     desligada temporariamente; usa-se somente o segmento ativo mais recente
     (após o último bloco de zeros).
  3. Bloco de >= MIN_ZEROS_CONSECUTIVOS zeros no final -> unidade desligada;
     a projeção é zero.
  4. Primeiro mês após a ligação muito inferior aos seguintes (< LIMIAR_MES_PARCIAL
     da mediana dos 6 meses seguintes) -> mês de ligação parcial, descartado.
  5. Células vazias dentro do período ativo -> interpoladas linearmente.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np

from . import config
from .datas import formatar_mes_ano

STATUS_ATIVA = "ATIVA"
STATUS_INATIVA = "INATIVA"        # nunca ligada (só zeros / vazio)
STATUS_DESLIGADA = "DESLIGADA"    # zeros consecutivos no final


@dataclass
class SeriePreparada:
    nome: str
    status: str
    datas: list[date]
    valores: np.ndarray
    notas: list[str] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.valores)


def _blocos_de_zeros(v: np.ndarray) -> list[tuple[int, int]]:
    """Retorna blocos (inicio, fim_exclusivo) de valores exatamente zero."""
    eh_zero = np.isclose(v, 0.0, atol=1e-12) & ~np.isnan(v)
    blocos, i, n = [], 0, len(v)
    while i < n:
        if eh_zero[i]:
            j = i
            while j < n and eh_zero[j]:
                j += 1
            blocos.append((i, j))
            i = j
        else:
            i += 1
    return blocos


def preparar_serie(nome: str, datas: list[date], valores: np.ndarray) -> SeriePreparada:
    v = np.asarray(valores, dtype=float)
    notas: list[str] = []

    validos = ~np.isnan(v) & ~np.isclose(np.nan_to_num(v), 0.0, atol=1e-12)
    if not validos.any():
        return SeriePreparada(nome, STATUS_INATIVA, [], np.array([]),
                              ["Sem nenhum valor diferente de zero no histórico: "
                               "unidade não ligada. Projeção = 0."])

    # 1. zeros / vazios iniciais
    ini = int(np.argmax(validos))
    if ini > 0:
        notas.append(f"Zeros iniciais de {formatar_mes_ano(datas[0])} a "
                     f"{formatar_mes_ano(datas[ini - 1])} desconsiderados (unidade ainda não ligada).")
    ultimo_valido = len(v) - 1 - int(np.argmax(validos[::-1]))

    # 3. zeros consecutivos no final -> desligada
    cauda = v[ultimo_valido + 1:]
    n_zeros_cauda = int(np.sum(~np.isnan(cauda) & np.isclose(np.nan_to_num(cauda), 0.0, atol=1e-12)))
    if n_zeros_cauda >= config.MIN_ZEROS_CONSECUTIVOS:
        notas.append(f"Últimos {len(cauda)} meses com zero (desde {formatar_mes_ano(datas[ultimo_valido + 1])}): "
                     "unidade considerada desligada. Projeção = 0.")
        return SeriePreparada(nome, STATUS_DESLIGADA, [], np.array([]), notas)

    seg_ini = ini
    # 2. blocos internos de zeros consecutivos
    for (a, b) in _blocos_de_zeros(v):
        if a > ini and (b - a) >= config.MIN_ZEROS_CONSECUTIVOS and b <= ultimo_valido:
            notas.append(f"{b - a} meses consecutivos com zero entre {formatar_mes_ano(datas[a])} e "
                         f"{formatar_mes_ano(datas[b - 1])}: considerado apenas o período ativo após "
                         "esse intervalo.")
            seg_ini = b
    houve_zeros_antes = seg_ini > 0

    seg_v = v[seg_ini:].copy()
    seg_d = list(datas[seg_ini:])

    # 4. mês de ligação parcial
    if houve_zeros_antes and len(seg_v) >= 4 and not np.isnan(seg_v[0]):
        seguintes = seg_v[1:7]
        seguintes = seguintes[~np.isnan(seguintes)]
        if len(seguintes) >= 3:
            med = float(np.median(seguintes))
            if med > 0 and seg_v[0] < config.LIMIAR_MES_PARCIAL * med:
                v0 = f"{seg_v[0]:.4f}".replace(".", ",")
                vm = f"{med:.4f}".replace(".", ",")
                notas.append(f"Primeiro mês após a ligação ({formatar_mes_ano(seg_d[0])}, valor {v0}) "
                             f"é inferior a {config.LIMIAR_MES_PARCIAL:.0%} da mediana dos meses "
                             f"seguintes ({vm}): tratado como mês de ligação parcial e descartado.")
                seg_v, seg_d = seg_v[1:], seg_d[1:]

    # 5. valores ausentes no período ativo
    nan_mask = np.isnan(seg_v)
    if nan_mask.any():
        idx = np.arange(len(seg_v))
        seg_v[nan_mask] = np.interp(idx[nan_mask], idx[~nan_mask], seg_v[~nan_mask])
        notas.append(f"{int(nan_mask.sum())} valor(es) ausente(s) no período ativo preenchido(s) por "
                     "interpolação linear.")

    zeros_isolados = [formatar_mes_ano(seg_d[i]) for i in range(len(seg_v))
                      if np.isclose(seg_v[i], 0.0, atol=1e-12)]
    if zeros_isolados:
        notas.append("Zero(s) isolado(s) mantido(s) no período ativo (verificar se é falha de medição): "
                     + ", ".join(zeros_isolados) + ".")

    return SeriePreparada(nome, STATUS_ATIVA, seg_d, seg_v, notas)
