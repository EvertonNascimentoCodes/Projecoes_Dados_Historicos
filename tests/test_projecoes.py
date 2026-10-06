"""
Testes automatizados do projeto.  Executar na pasta do projeto:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from projecoes import metodologias as met  # noqa: E402
from projecoes.consistencia import criar_identidade, detectar_totais  # noqa: E402
from projecoes.datas import interpretar_mes_ano, sequencia_mensal  # noqa: E402
from projecoes.exportacao import formatar_numero, gravar_resultados  # noqa: E402
from projecoes.leitura import ErroLeitura, ler_dados_historicos  # noqa: E402
from projecoes.motor import definir_parametros, projetar_todas  # noqa: E402
from projecoes.preparacao import (STATUS_ATIVA, STATUS_DESLIGADA, STATUS_INATIVA,  # noqa: E402
                                  preparar_serie)
from projecoes.validacao import avaliar_e_selecionar  # noqa: E402

DATAS = sequencia_mensal(date(2021, 1, 1), date(2026, 9, 1))


def serie_sazonal(n=69, nivel=100.0, tend=0.5, amp=15.0, ruido=0.0, seed=1):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    return nivel + tend * t + amp * np.sin(2 * np.pi * t / 12) + rng.normal(0, ruido, n)


def escrever_csv(pasta: Path, linhas: list[str]) -> Path:
    p = pasta / "DadosHistoricos.csv"
    p.write_text("\n".join(linhas), encoding="utf-8")
    return p


class TestDatas(unittest.TestCase):
    def test_formatos(self):
        self.assertEqual(interpretar_mes_ano("10/2026"), date(2026, 10, 1))
        self.assertEqual(interpretar_mes_ano("1-2027"), date(2027, 1, 1))
        self.assertEqual(interpretar_mes_ano("01/03/2027"), date(2027, 3, 1))
        with self.assertRaises(ValueError):
            interpretar_mes_ano("13/2026")
        with self.assertRaises(ValueError):
            interpretar_mes_ano("2026")


class TestPreparacao(unittest.TestCase):
    def test_zeros_iniciais_e_mes_parcial(self):
        v = np.r_[np.zeros(10), 0.05, np.full(20, 30.0)]
        s = preparar_serie("X", DATAS[:31], v)
        self.assertEqual(s.status, STATUS_ATIVA)
        self.assertEqual(s.n, 20)            # 10 zeros + mês parcial descartados
        self.assertEqual(s.datas[0], DATAS[11])

    def test_bloco_interno_de_zeros(self):
        v = np.r_[np.full(10, 5.0), 0, 0, 0, np.full(10, 7.0)]
        s = preparar_serie("X", DATAS[:23], v)
        self.assertEqual(s.n, 10)
        self.assertTrue(np.all(s.valores == 7.0))

    def test_zero_isolado_mantido(self):
        v = np.r_[np.full(10, 5.0), 0, np.full(10, 7.0)]
        s = preparar_serie("X", DATAS[:21], v)
        self.assertEqual(s.n, 21)

    def test_desligada_e_inativa(self):
        v = np.r_[np.full(10, 5.0), 0, 0]
        self.assertEqual(preparar_serie("X", DATAS[:12], v).status, STATUS_DESLIGADA)
        self.assertEqual(preparar_serie("X", DATAS[:12], np.zeros(12)).status, STATUS_INATIVA)

    def test_ausentes_interpolados(self):
        v = np.r_[10.0, np.nan, 30.0, 40.0]
        s = preparar_serie("X", DATAS[:4], v)
        self.assertAlmostEqual(s.valores[1], 20.0)


class TestMetodologias(unittest.TestCase):
    def test_todas_retornam_horizonte_correto(self):
        y = serie_sazonal(ruido=2)
        for m in met.CATALOGO:
            if m.funcao is None:
                continue
            p = m.funcao(y, 51)
            self.assertEqual(p.shape, (51,), m.nome)
            self.assertTrue(np.all(np.isfinite(p)), m.nome)

    def test_holt_winters_recupera_serie_sem_ruido(self):
        y = serie_sazonal(n=72)
        real = serie_sazonal(n=84)[72:]
        for f in (met.holt_winters_aditivo, met.regressao_linear_sazonal):
            p = f(y, 12)
            self.assertLess(np.max(np.abs(p - real) / real), 0.03, f.__name__)

    def test_naive_sazonal(self):
        y = np.arange(1, 25, dtype=float)
        np.testing.assert_allclose(met.naive_sazonal(y, 14), np.r_[np.arange(13, 25), 13, 14])

    def test_multiplicativo_rejeita_nao_positivos(self):
        y = serie_sazonal()
        y[5] = 0
        with self.assertRaises(met.MetodoNaoAplicavel):
            met.holt_winters_multiplicativo(y, 12)


class TestSelecao(unittest.TestCase):
    def test_serie_sazonal_escolhe_metodo_sazonal(self):
        sel = avaliar_e_selecionar(serie_sazonal(ruido=1.0), 24)
        self.assertIn(sel.escolhido, {"HoltWinters_Aditivo", "HoltWinters_Multiplicativo",
                                      "Regressao_Linear_Sazonal", "Combinacao_Modelos", "Theta",
                                      "Sazonal_Crescimento", "Autoregressivo_Sazonal"})
        self.assertEqual(len(sel.previsao), 24)

    def test_serie_constante_projeta_nivel_correto(self):
        y = 50 + np.random.default_rng(3).normal(0, 1, 60)
        sel = avaliar_e_selecionar(y, 48)
        self.assertLess(np.max(np.abs(sel.previsao - 50)), 2.5)

    def test_serie_curta_sem_tendencia(self):
        y = np.array([29.2, 33.2, 28.9, 27.6, 27.2, 27.8, 26.8, 26.2])
        sel = avaliar_e_selecionar(y, 51)
        for nome in ("Theta", "Regressao_Linear", "Holt_Amortecido"):
            self.assertEqual(sel.resultados[nome].status, "NAO_ELEGIVEL")

    def test_serie_muito_curta(self):
        sel = avaliar_e_selecionar(np.array([10.0, 12.0, 11.0]), 5)
        self.assertEqual(sel.escolhido, "Media_Simples")
        np.testing.assert_allclose(sel.previsao, 11.0)


class TestLeituraEFluxo(unittest.TestCase):
    def test_erros_de_leitura(self):
        with tempfile.TemporaryDirectory() as d:
            p = escrever_csv(Path(d), ["DATA;A", "01/01/2021;1,0", "01/03/2021;2,0"])
            with self.assertRaises(ErroLeitura):
                ler_dados_historicos(p)
            p = escrever_csv(Path(d), ["DATA;A", "01/01/2021;abc"])
            with self.assertRaises(ErroLeitura):
                ler_dados_historicos(p)

    def test_fluxo_completo_com_identidade_e_retroativo(self):
        a = serie_sazonal(ruido=1, seed=1)
        b = np.r_[np.zeros(20), serie_sazonal(n=49, nivel=40, ruido=1, seed=2)]
        liq = 400 + np.random.default_rng(4).normal(0, 3, 69)
        total = a + b + liq
        linhas = ["DATA;TOTAL;A;B;LIQUIDA"]
        for i, d in enumerate(DATAS):
            linhas.append(f"{d:%d/%m/%Y};" + ";".join(formatar_numero(x) for x in
                                                       (total[i], a[i], b[i], liq[i])))
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            dados = ler_dados_historicos(escrever_csv(pasta, linhas))
            totais = detectar_totais(dados.medicoes, dados.valores)
            self.assertEqual(len(totais), 1)
            self.assertEqual(totais[0].base, "TOTAL")
            self.assertEqual(totais[0].sugestao_derivada(), "LIQUIDA")
            ident = criar_identidade(totais[0], "LIQUIDA")

            # início dentro do histórico (modo retroativo)
            params = definir_parametros(dados, date(2025, 10, 1), date(2027, 12, 1))
            self.assertEqual(params.fim_treino, date(2025, 9, 1))
            self.assertEqual(params.horizonte, 27)
            res = projetar_todas(dados, params)
            proj = {m: res[m].projecao for m in dados.medicoes}
            np.testing.assert_allclose(ident.calcular(proj),
                                       proj["TOTAL"] - proj["A"] - proj["B"])
            arqs = gravar_resultados(pasta, params.datas_saida, dados.medicoes, proj)
            self.assertEqual(len(arqs), 4)

            # início após o fim do histórico (meses intermediários não gravados)
            params = definir_parametros(dados, date(2027, 1, 1), date(2027, 12, 1))
            self.assertEqual(params.deslocamento_saida, 3)
            self.assertEqual(len(params.datas_saida), 12)


if __name__ == "__main__":
    unittest.main()
