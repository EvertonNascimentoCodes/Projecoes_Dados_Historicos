"""Orquestra a projeção de todas as medições."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np

from .consistencia import Identidade
from .datas import indice_mes, meses_entre, sequencia_mensal, somar_meses
from .diagnostico import Diagnostico, diagnosticar
from .leitura import DadosHistoricos
from .preparacao import STATUS_ATIVA, SeriePreparada, preparar_serie
from .validacao import ResultadoSelecao, avaliar_e_selecionar

METODO_ZERO = "Sem_Projecao_Zero"
METODO_IDENTIDADE = "Identidade"


@dataclass
class ResultadoMedicao:
    nome: str
    serie: SeriePreparada
    diagnostico: Diagnostico | None
    selecao: ResultadoSelecao | None
    projecao: np.ndarray                      # horizonte completo (fim_treino+1 .. fim)
    metodo_final: str
    identidade: Identidade | None = None
    projecao_independente: np.ndarray | None = None
    notas: list[str] = field(default_factory=list)


@dataclass
class ParametrosProjecao:
    inicio: date
    fim: date
    fim_treino: date

    @property
    def horizonte(self) -> int:
        return meses_entre(self.fim_treino, self.fim)

    @property
    def deslocamento_saida(self) -> int:
        """Quantos meses projetados ficam antes do início pedido (não são gravados)."""
        return meses_entre(self.fim_treino, self.inicio) - 1

    @property
    def datas_saida(self) -> list[date]:
        return sequencia_mensal(self.inicio, self.fim)


def definir_parametros(dados: DadosHistoricos, inicio: date, fim: date) -> ParametrosProjecao:
    if indice_mes(fim) < indice_mes(inicio):
        raise ValueError("O mês final da projeção deve ser igual ou posterior ao mês inicial.")
    if indice_mes(inicio) <= indice_mes(dados.primeira_data):
        raise ValueError("O mês inicial deve ser posterior ao primeiro mês do histórico "
                         "(é necessário ao menos um mês de dados para treinar os modelos).")
    fim_treino = min(dados.ultima_data, somar_meses(inicio, -1), key=indice_mes)
    return ParametrosProjecao(inicio, fim, fim_treino)


def projetar_medicao(nome: str, datas: list[date], valores: np.ndarray,
                     params: ParametrosProjecao) -> ResultadoMedicao:
    H = params.horizonte
    serie = preparar_serie(nome, datas, valores)
    if serie.status != STATUS_ATIVA or serie.n == 0:
        return ResultadoMedicao(nome, serie, None, None, np.zeros(H), METODO_ZERO)
    diag = diagnosticar(serie.valores)
    selecao = avaliar_e_selecionar(serie.valores, H)
    return ResultadoMedicao(nome, serie, diag, selecao, selecao.previsao.copy(), selecao.escolhido)


def projetar_todas(dados: DadosHistoricos, params: ParametrosProjecao,
                   progresso=None) -> dict[str, ResultadoMedicao]:
    n_treino = meses_entre(dados.primeira_data, params.fim_treino) + 1
    datas_treino = dados.datas[:n_treino]
    resultados = {}
    for k, nome in enumerate(dados.medicoes, start=1):
        if progresso:
            progresso(k, len(dados.medicoes), nome)
        resultados[nome] = projetar_medicao(nome, datas_treino, dados.valores[nome][:n_treino], params)
    return resultados


def aplicar_identidades(resultados: dict[str, ResultadoMedicao], identidades: list[Identidade]) -> None:
    proj = {n: r.projecao for n, r in resultados.items()}
    for ident in identidades:
        r = resultados[ident.derivada]
        r.projecao_independente = r.projecao.copy()
        r.projecao = ident.calcular(proj)
        r.identidade = ident
        r.metodo_final = METODO_IDENTIDADE
        proj[ident.derivada] = r.projecao
        if np.any(r.projecao < 0):
            r.notas.append("ATENÇÃO: a identidade resultou em valores negativos em algum mês "
                           "(a soma projetada das parcelas superou a base).")
