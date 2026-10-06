"""
Diagnóstico estatístico da série: força da sazonalidade, tendência,
variabilidade. Usado para explicar (no relatório) por que a metodologia
escolhida é coerente com o comportamento dos dados.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats

from . import config

M = config.PERIODO_SAZONAL


@dataclass
class Diagnostico:
    n: int
    media: float
    coef_variacao: float              # desvio padrão / média
    forca_sazonal: float | None       # 0 a 1 (None se < 36 meses)
    tendencia_pct_ano: float | None   # % ao ano em relação à média
    tendencia_p_valor: float | None
    crescimento_12m: float | None     # últimos 12 meses vs 12 anteriores

    def texto_sazonalidade(self) -> str:
        if self.forca_sazonal is None:
            return "sazonalidade não mensurável (menos de 36 meses de histórico)"
        f = self.forca_sazonal
        if f >= 0.64:
            nivel = "forte"
        elif f >= 0.40:
            nivel = "moderada"
        elif f >= 0.20:
            nivel = "fraca"
        else:
            nivel = "ausente/irrelevante"
        return f"sazonalidade {nivel} (força sazonal {f:.2f})".replace(".", ",")

    def texto_caracteristicas(self) -> str:
        return (f"{self.texto_sazonalidade()}; {self.texto_tendencia()}; "
                f"{self.texto_variabilidade()}")

    def texto_tendencia(self) -> str:
        if self.tendencia_pct_ano is None:
            return "tendência não mensurável"
        p = self.tendencia_p_valor
        t = self.tendencia_pct_ano
        if p is not None and p < 0.05:
            sentido = "alta" if t > 0 else "queda"
            return (f"tendência de {sentido} estatisticamente significativa "
                    f"({t:+.1f}% ao ano, p={p:.3f})").replace(".", ",")
        return f"sem tendência estatisticamente significativa ({t:+.1f}% ao ano, p={p:.2f})".replace(".", ",")

    def texto_variabilidade(self) -> str:
        cv = self.coef_variacao
        if cv < 0.05:
            nivel = "muito baixa"
        elif cv < 0.15:
            nivel = "baixa"
        elif cv < 0.30:
            nivel = "moderada"
        else:
            nivel = "alta"
        cv_txt = f"{cv * 100:.1f}%".replace(".", ",")
        return f"variabilidade {nivel} (coeficiente de variação {cv_txt})"


def media_movel_centrada(y: np.ndarray, m: int = M) -> np.ndarray:
    """Média móvel centrada 2xm (para m par), NaN nas bordas."""
    n = len(y)
    out = np.full(n, np.nan)
    meio = m // 2
    if n < m + 1:
        return out
    pesos = np.r_[0.5, np.ones(m - 1), 0.5] / m
    for t in range(meio, n - meio):
        out[t] = float(np.dot(pesos, y[t - meio:t + meio + 1]))
    return out


def decomposicao_aditiva(y: np.ndarray, m: int = M):
    """Decomposição clássica aditiva. Retorna (tendencia, sazonal_por_posicao)."""
    tend = media_movel_centrada(y, m)
    det = y - tend
    saz = np.zeros(m)
    for p in range(m):
        vals = det[p::m]
        vals = vals[~np.isnan(vals)]
        saz[p] = vals.mean() if len(vals) else 0.0
    saz -= saz.mean()
    return tend, saz


def diagnosticar(y: np.ndarray) -> Diagnostico:
    y = np.asarray(y, dtype=float)
    n = len(y)
    media = float(np.mean(y)) if n else 0.0
    cv = float(np.std(y, ddof=1) / abs(media)) if n > 1 and media != 0 else 0.0

    forca = None
    ajustada = y
    # força sazonal exige ao menos 3 ciclos (com 2 ciclos cada mês teria uma
    # única observação de resíduo e a medida seria artificialmente 1,0)
    if n >= 3 * M:
        tend, saz = decomposicao_aditiva(y)
        pos = np.arange(n) % M
        det = y - tend
        ok = ~np.isnan(det)
        resto = det[ok] - saz[pos[ok]]
        var_det = np.var(det[ok])
        forca = float(max(0.0, 1.0 - np.var(resto) / var_det)) if var_det > 0 else 0.0
        ajustada = y - saz[pos]

    tend_pct, p_val = None, None
    if n >= 6 and media != 0:
        t = np.arange(n)
        reg = stats.linregress(t, ajustada)
        tend_pct = float(reg.slope * 12 / abs(media) * 100)
        p_val = float(reg.pvalue) if np.isfinite(reg.pvalue) else 1.0

    cresc = None
    if n >= 24:
        s0, s1 = y[-24:-12].sum(), y[-12:].sum()
        if s0 > 0:
            cresc = float(s1 / s0 - 1)

    return Diagnostico(n, media, cv, forca, tend_pct, p_val, cresc)
