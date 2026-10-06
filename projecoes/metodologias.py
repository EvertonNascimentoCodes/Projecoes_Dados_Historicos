"""
Catálogo de metodologias de projeção.

Todas as metodologias foram implementadas apenas com numpy/scipy, de forma
transparente e determinística. Cada uma recebe a série histórica `y`
(array 1-D, mensal, sem lacunas) e o horizonte `h` (meses) e devolve um
array com `h` valores projetados.

A sazonalidade é tratada pela posição relativa (t mod 12) a partir do início
da série, o que equivale ao mês do calendário, pois a série é contínua.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

import numpy as np
from scipy.optimize import minimize, minimize_scalar

from . import config
from .diagnostico import media_movel_centrada

M = config.PERIODO_SAZONAL
_PENALIDADE = 1e300


class MetodoNaoAplicavel(Exception):
    """A metodologia não pode ser aplicada a esta série (ex.: valores não positivos)."""


# ==========================================================================
# Funções auxiliares
# ==========================================================================
def _exigir(n: int, minimo: int, nome: str) -> None:
    if n < minimo:
        raise MetodoNaoAplicavel(f"{nome} exige ao menos {minimo} meses (há {n}).")


def indices_sazonais_multiplicativos(y: np.ndarray) -> np.ndarray:
    """Índices sazonais clássicos (razão à média móvel centrada), média = 1."""
    if np.any(y <= 0):
        raise MetodoNaoAplicavel("índices multiplicativos exigem valores positivos.")
    mm = media_movel_centrada(y, M)
    razao = y / mm
    idx = np.ones(M)
    for p in range(M):
        r = razao[p::M]
        r = r[~np.isnan(r)]
        if len(r) == 0:
            raise MetodoNaoAplicavel("histórico insuficiente para índices sazonais.")
        idx[p] = r.mean()
    return idx / idx.mean()


def _autocorrelacao(y: np.ndarray, k: int) -> float:
    yc = y - y.mean()
    den = float(np.dot(yc, yc))
    return float(np.dot(yc[:-k], yc[k:]) / den) if den > 0 else 0.0


def sazonalidade_significativa(y: np.ndarray) -> bool:
    """Teste da autocorrelação no lag 12 (90%, como no método Theta clássico)."""
    n = len(y)
    if n < 2 * M + 1:
        return False
    r = [_autocorrelacao(y, k) for k in range(1, M + 1)]
    limite = 1.645 * math.sqrt((1 + 2 * sum(x * x for x in r[:-1])) / n)
    return abs(r[-1]) > limite


def _otimizar(func, x0_lista, limites, args):
    melhor = None
    for x0 in x0_lista:
        try:
            res = minimize(func, x0=np.array(x0), args=args, method="L-BFGS-B", bounds=limites)
        except (FloatingPointError, ValueError, OverflowError):
            continue
        if np.isfinite(res.fun) and (melhor is None or res.fun < melhor.fun):
            melhor = res
    if melhor is None or melhor.fun >= _PENALIDADE:
        raise MetodoNaoAplicavel("otimização dos parâmetros não convergiu.")
    return melhor.x


# ==========================================================================
# Métodos simples
# ==========================================================================
def media_simples(y: np.ndarray, h: int) -> np.ndarray:
    _exigir(len(y), 1, "Média simples")
    return np.full(h, float(np.mean(y[-M:])))


def media_movel_3m(y: np.ndarray, h: int) -> np.ndarray:
    _exigir(len(y), 3, "Média móvel 3M")
    return np.full(h, float(np.mean(y[-3:])))


def naive_sazonal(y: np.ndarray, h: int) -> np.ndarray:
    n = len(y)
    _exigir(n, M, "Naive sazonal")
    return np.array([y[n - M + (k % M)] for k in range(h)], dtype=float)


def media_sazonal(y: np.ndarray, h: int) -> np.ndarray:
    """Nível dos últimos 12 meses x índices sazonais médios de todo o histórico."""
    n = len(y)
    _exigir(n, 2 * M, "Média sazonal")
    nivel = float(np.mean(y[-M:]))
    idx = indices_sazonais_multiplicativos(y)
    return np.array([nivel * idx[(n + k) % M] for k in range(h)])


def sazonal_crescimento(y: np.ndarray, h: int) -> np.ndarray:
    """Repete o último ano aplicando o crescimento anual observado (últ. 12m / 12m anteriores)."""
    n = len(y)
    _exigir(n, 2 * M, "Sazonal com crescimento")
    s0, s1 = float(y[-2 * M:-M].sum()), float(y[-M:].sum())
    if s0 <= 0 or s1 <= 0:
        raise MetodoNaoAplicavel("somas anuais não positivas.")
    g = s1 / s0
    return np.array([y[n - M + (k % M)] * g ** (k // M + 1) for k in range(h)])


# ==========================================================================
# Regressões
# ==========================================================================
def regressao_linear(y: np.ndarray, h: int) -> np.ndarray:
    n = len(y)
    _exigir(n, 4, "Regressão linear")
    t = np.arange(n)
    b, a = np.polyfit(t, y, 1)
    return a + b * np.arange(n, n + h)


def _matriz_sazonal(t: np.ndarray) -> np.ndarray:
    X = np.zeros((len(t), 2 + M - 1))
    X[:, 0] = 1.0
    X[:, 1] = t
    pos = t % M
    for p in range(1, M):
        X[:, 1 + p] = (pos == p).astype(float)
    return X


def regressao_linear_sazonal(y: np.ndarray, h: int) -> np.ndarray:
    n = len(y)
    _exigir(n, 2 * M, "Regressão linear sazonal")
    coef, *_ = np.linalg.lstsq(_matriz_sazonal(np.arange(n)), y, rcond=None)
    return _matriz_sazonal(np.arange(n, n + h)) @ coef


def autoregressivo_sazonal(y: np.ndarray, h: int) -> np.ndarray:
    """y_t = c + a1*y_(t-1) + a12*y_(t-12), mínimos quadrados, previsão recursiva."""
    n = len(y)
    _exigir(n, 3 * M, "Autorregressivo sazonal")
    t = np.arange(M, n)
    X = np.column_stack([np.ones(len(t)), y[t - 1], y[t - M]])
    coef, *_ = np.linalg.lstsq(X, y[t], rcond=None)
    if abs(coef[1]) + abs(coef[2]) >= 1.0:
        raise MetodoNaoAplicavel("modelo autorregressivo não estacionário (explosivo).")
    ext = list(y.astype(float))
    for _ in range(h):
        ext.append(coef[0] + coef[1] * ext[-1] + coef[2] * ext[-M])
    return np.array(ext[n:])


# ==========================================================================
# Suavização exponencial
# ==========================================================================
def _ses_sse(alpha: float, y: np.ndarray) -> float:
    nivel, sse = y[0], 0.0
    for v in y[1:]:
        e = v - nivel
        sse += e * e
        nivel += alpha * e
    return sse


def ajustar_ses(y: np.ndarray) -> tuple[float, float]:
    """Retorna (alpha, nível final)."""
    if len(y) < 2:
        return 1.0, float(y[-1])
    res = minimize_scalar(_ses_sse, bounds=(0.01, 0.99), args=(y,), method="bounded")
    alpha = float(res.x)
    nivel = y[0]
    for v in y[1:]:
        nivel += alpha * (v - nivel)
    return alpha, float(nivel)


def ses(y: np.ndarray, h: int) -> np.ndarray:
    _exigir(len(y), 4, "Suavização exponencial simples")
    _, nivel = ajustar_ses(y)
    return np.full(h, nivel)


def _estado_inicial_holt(y: np.ndarray) -> tuple[float, float]:
    k = min(len(y), M)
    b, a = np.polyfit(np.arange(k), y[:k], 1)
    return float(a - b), float(b)   # nível e tendência em t = -1


def _holt_rec(params, y, retornar=False):
    alpha, beta, phi = params
    l, b = _estado_inicial_holt(y)
    sse = 0.0
    for v in y:
        prev = l + phi * b
        e = v - prev
        sse += e * e
        l_novo = prev + alpha * e
        b = beta * (l_novo - l) + (1 - beta) * phi * b
        l = l_novo
    if not np.isfinite(sse):
        sse = _PENALIDADE
    return (l, b) if retornar else sse


def holt_amortecido(y: np.ndarray, h: int) -> np.ndarray:
    _exigir(len(y), 6, "Holt amortecido")
    p = _otimizar(_holt_rec, [(0.3, 0.05, 0.95), (0.6, 0.1, 0.9), (0.1, 0.01, 0.98)],
                  [(0.01, 0.99), (0.0001, 0.5), (0.80, 0.98)], (y,))
    l, b = _holt_rec(p, y, retornar=True)
    phi = p[2]
    soma_phi = np.cumsum(phi ** np.arange(1, h + 1))
    return l + soma_phi * b


def _hw_rec(params, y, multiplicativo, retornar=False):
    alpha, beta, gamma, phi = params
    # estado inicial: nível médio do 1º ano (centrado em t = 5,5), tendência pela
    # diferença entre as médias dos dois primeiros anos e sazonalidade do 1º ano
    # descontada a tendência (evita que a tendência contamine os fatores sazonais)
    centro = (M - 1) / 2
    l_c = float(np.mean(y[:M]))
    b = float((np.mean(y[M:2 * M]) - l_c) / M)
    base = l_c + b * (np.arange(M) - centro)
    if multiplicativo:
        if np.any(base <= 0):
            return _PENALIDADE if not retornar else None
        s = y[:M] / base
    else:
        s = y[:M] - base
    s = s.astype(float).copy()
    l = l_c - b * (centro + 1)          # nível em t = -1
    sse = 0.0
    for t, v in enumerate(y):
        i = t % M
        prev = l + phi * b
        if multiplicativo:
            if prev <= 0 or s[i] <= 0:
                return _PENALIDADE if not retornar else None
            yhat = prev * s[i]
        else:
            yhat = prev + s[i]
        e = v - yhat
        sse += e * e
        if multiplicativo:
            l_novo = alpha * (v / s[i]) + (1 - alpha) * prev
            s[i] = gamma * (v / prev) + (1 - gamma) * s[i]
        else:
            l_novo = alpha * (v - s[i]) + (1 - alpha) * prev
            s[i] = gamma * (v - prev) + (1 - gamma) * s[i]
        b = beta * (l_novo - l) + (1 - beta) * phi * b
        l = l_novo
    if retornar:
        return l, b, s
    return sse if np.isfinite(sse) else _PENALIDADE


def _holt_winters(y: np.ndarray, h: int, multiplicativo: bool) -> np.ndarray:
    n = len(y)
    nome = "Holt-Winters multiplicativo" if multiplicativo else "Holt-Winters aditivo"
    _exigir(n, 2 * M, nome)
    if multiplicativo and np.any(y <= 0):
        raise MetodoNaoAplicavel("Holt-Winters multiplicativo exige valores positivos.")
    p = _otimizar(_hw_rec,
                  [(0.3, 0.02, 0.1, 0.95), (0.6, 0.05, 0.2, 0.9), (0.1, 0.01, 0.05, 0.98)],
                  [(0.01, 0.99), (0.0001, 0.3), (0.0001, 0.6), (0.80, 0.98)],
                  (y, multiplicativo))
    estado = _hw_rec(p, y, multiplicativo, retornar=True)
    if estado is None:
        raise MetodoNaoAplicavel("estado do modelo inválido.")
    l, b, s = estado
    phi = p[3]
    soma_phi = np.cumsum(phi ** np.arange(1, h + 1))
    pos = (n + np.arange(h)) % M
    base = l + soma_phi * b
    return base * s[pos] if multiplicativo else base + s[pos]


def holt_winters_aditivo(y: np.ndarray, h: int) -> np.ndarray:
    return _holt_winters(y, h, multiplicativo=False)


def holt_winters_multiplicativo(y: np.ndarray, h: int) -> np.ndarray:
    return _holt_winters(y, h, multiplicativo=True)


def theta(y: np.ndarray, h: int) -> np.ndarray:
    """Método Theta clássico (Assimakopoulos & Nikolopoulos, 2000; forma de Hyndman & Billah).

    Dessazonaliza (multiplicativo) quando a sazonalidade é significativa,
    combina suavização exponencial simples com metade da tendência linear.
    """
    n = len(y)
    _exigir(n, 4, "Theta")
    idx = None
    ys = y.astype(float)
    if n >= 2 * M and np.all(y > 0) and sazonalidade_significativa(y):
        idx = indices_sazonais_multiplicativos(y)
        ys = y / idx[np.arange(n) % M]
    alpha, nivel = ajustar_ses(ys)
    alpha = max(alpha, 1e-10)
    b0 = np.polyfit(np.arange(n), ys, 1)[0]
    k = np.arange(h)
    prev = nivel + 0.5 * b0 * (k + (1 - (1 - alpha) ** n) / alpha)
    if idx is not None:
        prev = prev * idx[(n + k) % M]
    return prev


# ==========================================================================
# Catálogo
# ==========================================================================
@dataclass(frozen=True)
class Metodologia:
    nome: str                 # usado em arquivos (sem espaços/acentos)
    titulo: str               # nome legível
    descricao: str            # o que o método captura
    complexidade: int         # para o critério de parcimônia
    min_obs: int              # mínimo de meses para ajustar
    funcao: Callable[[np.ndarray, int], np.ndarray] | None
    usa_tendencia: bool = False   # extrapola tendência (ver MIN_MESES_TENDENCIA)


NOME_COMBINACAO = "Combinacao_Modelos"

CATALOGO: list[Metodologia] = [
    Metodologia("Media_Simples", "Média simples (últimos 12 meses)",
                "projeta um nível constante igual à média dos últimos 12 meses; adequado a séries "
                "estáveis, sem tendência nem sazonalidade relevantes", 1, 1, media_simples),
    Metodologia("Media_Movel_3M", "Média móvel de 3 meses",
                "projeta o nível recente (média dos 3 últimos meses); reage rápido a mudanças "
                "de patamar, sem tendência nem sazonalidade", 1, 3, media_movel_3m),
    Metodologia("Naive_Sazonal", "Ingênuo sazonal",
                "repete o mesmo mês do último ano; adequado quando o perfil sazonal é estável "
                "e o nível não muda", 2, M, naive_sazonal),
    Metodologia("Suavizacao_Exponencial_Simples", "Suavização exponencial simples (SES)",
                "nível ponderado com pesos decrescentes no tempo; adequado a séries sem tendência "
                "nem sazonalidade, mas com nível que oscila", 2, 4, ses),
    Metodologia("Regressao_Linear", "Regressão linear (tendência)",
                "reta de tendência ajustada por mínimos quadrados; adequado a crescimento/queda "
                "constante sem sazonalidade", 2, 4, regressao_linear, True),
    Metodologia("Media_Sazonal", "Média sazonal (nível x índices sazonais)",
                "nível dos últimos 12 meses multiplicado por índices sazonais médios do "
                "histórico; adequado a sazonalidade estável sem tendência", 3, 2 * M, media_sazonal),
    Metodologia("Sazonal_Crescimento", "Sazonal com crescimento anual",
                "repete o perfil do último ano aplicando a taxa de crescimento anual observada; "
                "adequado a sazonalidade marcada com crescimento consistente", 3, 2 * M,
                sazonal_crescimento, True),
    Metodologia("Holt_Amortecido", "Holt com tendência amortecida",
                "suavização exponencial de nível e tendência, com a tendência perdendo força ao "
                "longo do horizonte; adequado a séries com tendência sem sazonalidade", 4, 6,
                holt_amortecido, True),
    Metodologia("Theta", "Método Theta",
                "combina suavização exponencial com meia tendência linear, dessazonalizando quando "
                "há sazonalidade significativa; método robusto, vencedor da competição M3", 4, 4, theta, True),
    Metodologia("Regressao_Linear_Sazonal", "Regressão linear com sazonalidade mensal",
                "tendência linear mais um efeito fixo para cada mês do ano; adequado a tendência "
                "constante com sazonalidade estável", 5, 2 * M, regressao_linear_sazonal, True),
    Metodologia("Autoregressivo_Sazonal", "Autorregressivo sazonal (AR 1 e 12)",
                "explica o mês atual pelo mês anterior e pelo mesmo mês do ano anterior; capta "
                "inércia e sazonalidade", 5, 3 * M, autoregressivo_sazonal, True),
    Metodologia("HoltWinters_Aditivo", "Holt-Winters aditivo (tendência amortecida)",
                "suavização exponencial de nível, tendência amortecida e sazonalidade aditiva "
                "(amplitude sazonal constante)", 6, 2 * M, holt_winters_aditivo, True),
    Metodologia("HoltWinters_Multiplicativo", "Holt-Winters multiplicativo (tendência amortecida)",
                "suavização exponencial de nível, tendência amortecida e sazonalidade "
                "multiplicativa (amplitude sazonal proporcional ao nível)", 6, 2 * M,
                holt_winters_multiplicativo, True),
    Metodologia(NOME_COMBINACAO, "Combinação de modelos (média)",
                "média aritmética das projeções dos modelos estruturais válidos (Theta, Holt "
                "amortecido, Holt-Winters, regressão sazonal, autorregressivo sazonal, sazonal com "
                "crescimento); a combinação reduz o erro de modelos individuais", 7, 0, None),
]

MEMBROS_COMBINACAO = [
    "Theta", "Holt_Amortecido", "HoltWinters_Aditivo", "HoltWinters_Multiplicativo",
    "Regressao_Linear_Sazonal", "Autoregressivo_Sazonal", "Sazonal_Crescimento",
]

POR_NOME: dict[str, Metodologia] = {m.nome: m for m in CATALOGO}
