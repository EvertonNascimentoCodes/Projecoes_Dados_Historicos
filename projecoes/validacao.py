"""
Avaliação e seleção da melhor metodologia para uma série.

Procedimento (validação cruzada temporal com origem móvel / backtesting):
  * Define-se um horizonte de teste h = min(12, n // 4) e até 4 janelas de
    teste ao final do histórico (origens deslocadas de max(1, h // 4) meses).
  * Cada metodologia é ajustada SOMENTE com os dados anteriores a cada origem
    e projeta os h meses seguintes, que são comparados com o realizado.
  * Métrica principal: WAPE = soma|erro| / soma|real| (média das janelas).
    Também se calcula o viés = soma(erro) / soma(real).
  * Só concorrem metodologias avaliadas em TODAS as janelas (comparação justa)
    e cuja projeção final passe na verificação de plausibilidade.
  * Critério de parcimônia: entre métodos com WAPE até TOLERANCIA_PARCIMONIA
    (relativo) acima do melhor, escolhe-se o de menor complexidade.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np

from . import config
from .metodologias import (CATALOGO, MEMBROS_COMBINACAO, NOME_COMBINACAO, POR_NOME,
                           MetodoNaoAplicavel, media_simples)

OK = "OK"
REPROVADO = "REPROVADO"
FALHOU = "FALHOU"
NAO_ELEGIVEL = "NAO_ELEGIVEL"


@dataclass
class ResultadoMetodo:
    nome: str
    status: str
    motivo: str = ""
    wape: float = float("nan")
    bias: float = float("nan")
    previsoes_dobras: list[np.ndarray] = field(default_factory=list)
    previsao_final: np.ndarray | None = None


@dataclass
class ResultadoSelecao:
    escolhido: str
    regra: str                        # menor_erro | parcimonia | fallback | sem_validacao
    resultados: dict[str, ResultadoMetodo]
    h_cv: int | None
    origens: list[int]
    melhor_por_erro: str | None = None
    membros_combinacao: list[str] = field(default_factory=list)

    @property
    def previsao(self) -> np.ndarray:
        return self.resultados[self.escolhido].previsao_final

    def ranking(self) -> list[ResultadoMetodo]:
        ordem = {OK: 0, REPROVADO: 1, FALHOU: 2, NAO_ELEGIVEL: 3}
        return sorted(self.resultados.values(),
                      key=lambda r: (ordem[r.status],
                                     r.wape if np.isfinite(r.wape) else np.inf,
                                     POR_NOME[r.nome].complexidade if r.nome in POR_NOME else 99))


def definir_dobras(n: int) -> tuple[int | None, list[int]]:
    if n < config.N_MIN_VALIDACAO:
        return None, []
    h = min(config.CV_HORIZONTE_MAX, max(1, n // 4))
    passo = max(1, h // 4)
    origens = []
    for k in range(config.CV_MAX_DOBRAS):
        o = n - h - k * passo
        if o >= config.CV_MIN_TREINO:
            origens.append(o)
    return h, origens


def _metricas(y: np.ndarray, origens: list[int], h: int, prevs: list[np.ndarray]) -> tuple[float, float]:
    wapes, biases = [], []
    for o, p in zip(origens, prevs):
        real = y[o:o + h]
        erro = p - real
        den = np.sum(np.abs(real))
        if den > 0:
            wapes.append(np.sum(np.abs(erro)) / den)
            biases.append(np.sum(erro) / den)
        else:
            wapes.append(0.0 if np.allclose(erro, 0) else np.inf)
            biases.append(0.0)
    return float(np.mean(wapes)), float(np.mean(biases))


def verificar_plausibilidade(y: np.ndarray, prev: np.ndarray) -> str:
    """Retorna string vazia se plausível; senão o motivo da reprovação."""
    if prev is None or len(prev) == 0:
        return "projeção vazia"
    if not np.all(np.isfinite(prev)):
        return "projeção com valores não numéricos/infinitos"
    if np.all(y >= 0) and np.any(prev < -1e-9):
        return "projeção com valores negativos (histórico só tem valores não negativos)"
    ref = float(np.mean(y[-config.PERIODO_SAZONAL:]))
    if ref > 0:
        r1 = float(np.mean(prev[:config.PERIODO_SAZONAL])) / ref
        r2 = float(np.mean(prev[-config.PERIODO_SAZONAL:])) / ref
        lo1, hi1 = config.PLAUS_RAZAO_PRIMEIROS_12
        lo2, hi2 = config.PLAUS_RAZAO_ULTIMOS_12
        if not lo1 <= r1 <= hi1:
            return (f"primeiros 12 meses projetados = {r1:.2f}x a média dos últimos 12 meses "
                    f"(aceito {lo1}x a {hi1}x)").replace(".", ",")
        if not lo2 <= r2 <= hi2:
            return (f"últimos 12 meses projetados = {r2:.2f}x a média dos últimos 12 meses "
                    f"históricos (aceito {lo2}x a {hi2}x): extrapolação explosiva").replace(".", ",")
    return ""


def avaliar_e_selecionar(y: np.ndarray, horizonte: int) -> ResultadoSelecao:
    y = np.asarray(y, dtype=float)
    n = len(y)
    h, origens = definir_dobras(n)
    resultados: dict[str, ResultadoMetodo] = {}

    with warnings.catch_warnings(), np.errstate(all="ignore"):
        warnings.simplefilter("ignore")

        if not origens:
            r = ResultadoMetodo("Media_Simples", OK,
                                motivo=f"histórico de {n} meses insuficiente para validação",
                                previsao_final=media_simples(y, horizonte))
            return ResultadoSelecao("Media_Simples", "sem_validacao", {"Media_Simples": r}, None, [])

        min_treino = min(origens)
        for met in CATALOGO:
            if met.funcao is None:
                continue
            if met.min_obs > n:
                resultados[met.nome] = ResultadoMetodo(
                    met.nome, NAO_ELEGIVEL, f"exige {met.min_obs} meses de histórico (há {n})")
                continue
            if met.usa_tendencia and n < config.MIN_MESES_TENDENCIA:
                resultados[met.nome] = ResultadoMetodo(
                    met.nome, NAO_ELEGIVEL,
                    f"extrapola tendência; exige ao menos {config.MIN_MESES_TENDENCIA} meses de "
                    f"histórico ativo (há {n})")
                continue
            if met.min_obs > min_treino:
                resultados[met.nome] = ResultadoMetodo(
                    met.nome, NAO_ELEGIVEL,
                    f"exige {met.min_obs} meses de treino e a menor janela de "
                    f"validação tem {min_treino}")
                continue
            try:
                prevs = []
                for o in origens:
                    p = np.asarray(met.funcao(y[:o], h), dtype=float)
                    if p.shape != (h,) or not np.all(np.isfinite(p)):
                        raise MetodoNaoAplicavel("projeção não numérica na validação")
                    prevs.append(p)
                final = np.asarray(met.funcao(y, horizonte), dtype=float)
            except MetodoNaoAplicavel as exc:
                resultados[met.nome] = ResultadoMetodo(met.nome, FALHOU, str(exc))
                continue
            except Exception as exc:  # proteção: um método nunca derruba o processo
                resultados[met.nome] = ResultadoMetodo(met.nome, FALHOU, f"erro inesperado: {exc}")
                continue
            wape, bias = _metricas(y, origens, h, prevs)
            motivo = verificar_plausibilidade(y, final)
            resultados[met.nome] = ResultadoMetodo(
                met.nome, REPROVADO if motivo else OK, motivo, wape, bias, prevs, final)

        # ---- combinação de modelos
        membros = [m for m in MEMBROS_COMBINACAO
                   if m in resultados and resultados[m].status == OK]
        if len(membros) >= 2:
            prevs = [np.mean([resultados[m].previsoes_dobras[i] for m in membros], axis=0)
                     for i in range(len(origens))]
            final = np.mean([resultados[m].previsao_final for m in membros], axis=0)
            wape, bias = _metricas(y, origens, h, prevs)
            motivo = verificar_plausibilidade(y, final)
            resultados[NOME_COMBINACAO] = ResultadoMetodo(
                NOME_COMBINACAO, REPROVADO if motivo else OK,
                motivo or "média de: " + ", ".join(membros), wape, bias, prevs, final)
        else:
            resultados[NOME_COMBINACAO] = ResultadoMetodo(
                NOME_COMBINACAO, NAO_ELEGIVEL, "menos de 2 modelos estruturais válidos para combinar")

    validos = [r for r in resultados.values() if r.status == OK and np.isfinite(r.wape)]
    if not validos:
        r = resultados.get("Media_Simples")
        if r is None or r.previsao_final is None:
            r = ResultadoMetodo("Media_Simples", OK, previsao_final=media_simples(y, horizonte))
            resultados["Media_Simples"] = r
        r.status = OK
        return ResultadoSelecao("Media_Simples", "fallback", resultados, h, origens, None, membros)

    melhor = min(validos, key=lambda r: (r.wape, POR_NOME[r.nome].complexidade))
    limite = melhor.wape * (1 + config.TOLERANCIA_PARCIMONIA)
    candidatos = [r for r in validos if r.wape <= limite + 1e-15]
    escolhido = min(candidatos, key=lambda r: (POR_NOME[r.nome].complexidade, r.wape))
    regra = "menor_erro" if escolhido.nome == melhor.nome else "parcimonia"
    return ResultadoSelecao(escolhido.nome, regra, resultados, h, origens, melhor.nome, membros)
