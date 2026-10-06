"""Geração do relatório texto explicando a metodologia escolhida para cada medição."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np

from . import config
from .datas import formatar_mes_ano, meses_entre, somar_meses
from .leitura import DadosHistoricos
from .metodologias import POR_NOME, NOME_COMBINACAO
from .motor import METODO_IDENTIDADE, METODO_ZERO, ParametrosProjecao, ResultadoMedicao
from .validacao import FALHOU, NAO_ELEGIVEL, OK, REPROVADO

LARGURA = 100
_STATUS_TXT = {OK: "válido", REPROVADO: "reprovado", FALHOU: "não aplicável", NAO_ELEGIVEL: "não elegível"}


def _pct(v: float, sinal: bool = False) -> str:
    if v is None or not np.isfinite(v):
        return "-"
    return (f"{v * 100:+.2f}%" if sinal else f"{v * 100:.2f}%").replace(".", ",")


def _titulo(nome: str) -> str:
    if nome == METODO_IDENTIDADE:
        return "Identidade contábil"
    if nome == METODO_ZERO:
        return "Sem projeção (zero)"
    return POR_NOME[nome].titulo if nome in POR_NOME else nome


def _quebrar(texto: str, recuo: str = "  ") -> list[str]:
    palavras, linhas, atual = texto.split(), [], recuo
    for p in palavras:
        if len(atual) + len(p) + 1 > LARGURA and atual.strip():
            linhas.append(atual.rstrip())
            atual = recuo
        atual += p + " "
    if atual.strip():
        linhas.append(atual.rstrip())
    return linhas


def justificativa(r: ResultadoMedicao) -> str:
    if r.metodo_final == METODO_ZERO:
        return ("A medição não possui período ativo para projetar (sem ligação ou desligada), "
                "portanto a projeção é zero em todos os meses.")
    sel, diag = r.selecao, r.diagnostico
    if r.metodo_final == METODO_IDENTIDADE:
        ind = sel.resultados[sel.escolhido]
        erro = f"{r.identidade.erro_max:.4f}".replace(".", ",")
        return (f"Foi detectado que, em todo o histórico, {r.identidade.descricao()} (diferença máxima "
                f"de {erro}). Para manter a coerência entre as medições, a projeção foi calculada pela "
                "própria identidade a partir das projeções das demais medições. Se projetada de forma "
                f"independente, a melhor metodologia seria '{_titulo(sel.escolhido)}' (WAPE "
                f"{_pct(ind.wape)}); esse resultado aparece no ranking abaixo apenas como referência "
                "e também é gravado na pasta de metodologias, se solicitado.")

    met = POR_NOME[sel.escolhido]
    esc = sel.resultados[sel.escolhido]
    caract = f"Características da série: {diag.texto_caracteristicas()}."
    if sel.regra == "sem_validacao":
        return (f"{caract} Há apenas {diag.n} meses de histórico ativo, o que não permite validar "
                "metodologias com segurança; adotou-se a média simples dos meses disponíveis, a "
                "alternativa mais conservadora.")
    if sel.regra == "fallback":
        return (f"{caract} Nenhuma metodologia passou nos critérios de validação e plausibilidade; "
                "adotou-se a média simples dos últimos 12 meses como alternativa conservadora.")

    n_validos = sum(1 for x in sel.resultados.values() if x.status == OK)
    n_testados = sum(1 for x in sel.resultados.values() if x.status in (OK, REPROVADO))
    nj, hm = len(sel.origens), sel.h_cv
    janelas = (f"{nj} {'janelas' if nj > 1 else 'janela'} de teste de "
               f"{hm} {'meses' if hm > 1 else 'mês'}")
    if sel.regra == "menor_erro":
        motivo = (f"Entre {n_testados} metodologias testadas ({n_validos} válidas), "
                  f"'{met.titulo}' obteve o menor erro na validação cruzada temporal ({janelas}): "
                  f"WAPE de {_pct(esc.wape)} e viés de {_pct(esc.bias, True)}.")
    else:
        melhor = sel.resultados[sel.melhor_por_erro]
        motivo = (f"Entre {n_testados} metodologias testadas ({n_validos} válidas), o menor erro foi de "
                  f"'{_titulo(sel.melhor_por_erro)}' (WAPE {_pct(melhor.wape)}), porém "
                  f"'{met.titulo}' ficou dentro da tolerância de {config.TOLERANCIA_PARCIMONIA:.0%} "
                  f"(WAPE {_pct(esc.wape)}, viés {_pct(esc.bias, True)}) e é mais simples; pelo "
                  "princípio da parcimônia foi preferida, pois modelos mais simples tendem a ser "
                  "mais estáveis em horizontes longos.")
    como = f"Como funciona: {met.descricao}."
    if sel.escolhido == NOME_COMBINACAO:
        como += " Modelos combinados: " + ", ".join(_titulo(m) for m in sel.membros_combinacao) + "."
    return f"{caract} {motivo} {como}"


def _tabela_ranking(r: ResultadoMedicao) -> list[str]:
    sel = r.selecao
    linhas = [f"  {'#':>2}  {'Metodologia':<52} {'WAPE':>9} {'Viés':>9}  Situação",
              "  " + "-" * (LARGURA - 2)]
    pos = 0
    for res in sel.ranking():
        pos += 1
        marca = "*" if res.nome == sel.escolhido and r.metodo_final != METODO_IDENTIDADE else " "
        sit = _STATUS_TXT[res.status]
        if res.status != OK and res.motivo:
            sit += f": {res.motivo}"
        linhas.append(f" {marca}{pos:>2}  {_titulo(res.nome):<52} {_pct(res.wape):>9} "
                      f"{_pct(res.bias, True):>9}  {sit}")
    linhas.append("  (*) metodologia escolhida  |  WAPE = erro absoluto total / valor real total; "
                  "viés + = superestimou")
    return linhas


def gerar_relatorio(caminho: Path, arquivo_entrada: Path, dados: DadosHistoricos,
                    params: ParametrosProjecao, resultados: dict[str, ResultadoMedicao],
                    avisos_gerais: list[str]) -> Path:
    L: list[str] = []
    sep = "=" * LARGURA
    L += [sep, "RELATÓRIO DE METODOLOGIAS DE PROJEÇÃO".center(LARGURA), sep,
          f"Gerado em            : {datetime.now():%d/%m/%Y %H:%M}",
          f"Arquivo de entrada   : {arquivo_entrada.name}",
          f"Histórico disponível : {formatar_mes_ano(dados.primeira_data)} a "
          f"{formatar_mes_ano(dados.ultima_data)} ({len(dados.datas)} meses, {len(dados.medicoes)} medições)",
          f"Dados usados no ajuste: até {formatar_mes_ano(params.fim_treino)}",
          f"Período projetado    : {formatar_mes_ano(params.inicio)} a {formatar_mes_ano(params.fim)} "
          f"({len(params.datas_saida)} meses)", ""]

    # anos parciais
    anos = {}
    for d in params.datas_saida:
        anos[d.year] = anos.get(d.year, 0) + 1
    parciais = [f"{a} ({q} meses)" for a, q in anos.items() if q < 12]
    if parciais:
        L += _quebrar("Observação: nos totais anuais, os seguintes anos estão incompletos (somam apenas os "
                      "meses projetados): " + ", ".join(parciais) + ".", "") + [""]
    if avisos_gerais:
        L.append("AVISOS")
        for a in avisos_gerais:
            L += _quebrar("- " + a, "  ")
        L.append("")

    L += ["CRITÉRIOS UTILIZADOS", "-" * LARGURA]
    def _x(v: float) -> str:
        return f"{v:.2f}".rstrip("0").rstrip(".").replace(".", ",") + "x"

    p1, p2 = config.PLAUS_RAZAO_PRIMEIROS_12, config.PLAUS_RAZAO_ULTIMOS_12
    criterios = [
        "1. Período ativo: zeros consecutivos no início indicam unidade ainda não ligada e são "
        "descartados; blocos internos de zeros consecutivos fazem considerar apenas o período ativo "
        "mais recente; zeros consecutivos no final indicam unidade desligada (projeção zero). Um "
        "primeiro mês muito abaixo dos seguintes (ligação no meio do mês) também é descartado.",
        "2. Para cada medição foram testadas até 14 metodologias (médias, ingênuo sazonal, "
        "suavização exponencial, Holt amortecido, Holt-Winters aditivo/multiplicativo, Theta, "
        "regressões com e sem sazonalidade, autorregressivo sazonal, sazonal com crescimento e "
        "combinação de modelos). Metodologias que exigem mais histórico do que o disponível não "
        "são elegíveis; métodos que extrapolam tendência exigem ao menos "
        f"{config.MIN_MESES_TENDENCIA} meses de histórico ativo.",
        "3. Validação cruzada temporal (backtesting com origem móvel): cada metodologia é ajustada "
        "apenas com dados anteriores a cada janela e projeta os meses seguintes, comparando-se com "
        "o realizado. Métrica principal: WAPE (erro absoluto percentual ponderado), média das janelas. "
        "A validação mede o acerto até o tamanho da janela de teste; para horizontes mais longos a "
        "incerteza naturalmente aumenta.",
        "4. Plausibilidade: projeções finais com valores negativos, não numéricos ou explosivos "
        f"(média dos 12 primeiros meses fora de {_x(p1[0])} a {_x(p1[1])} ou dos 12 últimos fora "
        f"de {_x(p2[0])} a {_x(p2[1])} a média dos últimos 12 meses reais) são reprovadas.",
        f"5. Parcimônia: entre metodologias com WAPE até {config.TOLERANCIA_PARCIMONIA:.0%} "
        "(relativo) acima do melhor, escolhe-se a mais simples.",
        "6. Identidades contábeis detectadas entre medições (ex.: líquida = total - parcelas) podem "
        "ser preservadas calculando a medição derivada a partir das demais projeções.",
    ]
    for c in criterios:
        L += _quebrar(c, "  ")
    L.append("")

    L += ["RESUMO", "-" * LARGURA,
          f"  {'Medição':<20} {'Histórico usado':<22} {'Metodologia escolhida':<46} {'WAPE':>8}"]
    for nome in dados.medicoes:
        r = resultados[nome]
        if r.serie.n:
            hist = f"{formatar_mes_ano(r.serie.datas[0])}-{formatar_mes_ano(r.serie.datas[-1])} ({r.serie.n}m)"
        else:
            hist = "-"
        w = "-"
        if r.selecao and r.metodo_final != METODO_IDENTIDADE:
            w = _pct(r.selecao.resultados[r.selecao.escolhido].wape)
        L.append(f"  {nome:<20} {hist:<22} {_titulo(r.metodo_final):<46} {w:>8}")
    L.append("")

    L += ["DETALHAMENTO POR MEDIÇÃO", sep]
    for nome in dados.medicoes:
        r = resultados[nome]
        L += ["", f">>> {nome}", "-" * LARGURA]
        if r.serie.n:
            L.append(f"  Período considerado : {formatar_mes_ano(r.serie.datas[0])} a "
                     f"{formatar_mes_ano(r.serie.datas[-1])} ({r.serie.n} meses)")
        else:
            L.append("  Período considerado : nenhum (sem dados ativos)")
        L.append(f"  Metodologia         : {_titulo(r.metodo_final)}")
        for nota in r.serie.notas + r.notas:
            L += _quebrar("- " + nota, "  ")
        L.append("  Por que esta metodologia:")
        L += _quebrar(justificativa(r), "    ")

        # comparação com realizado quando o período projetado se sobrepõe ao histórico
        sobre = min(meses_entre(params.inicio, dados.ultima_data) + 1, len(params.datas_saida))
        if sobre > 0:
            ini_hist = meses_entre(dados.primeira_data, params.inicio)
            reais = dados.valores[nome][ini_hist:ini_hist + sobre]
            prev = r.projecao[params.deslocamento_saida:params.deslocamento_saida + sobre]
            ok = ~np.isnan(reais)
            den = np.sum(np.abs(reais[ok]))
            if den > 0:
                wape = np.sum(np.abs(prev[ok] - reais[ok])) / den
                L.append(f"  Comparação com o realizado ({formatar_mes_ano(params.inicio)} a "
                         f"{formatar_mes_ano(somar_meses(params.inicio, sobre - 1))}): WAPE {_pct(wape)}")
        if r.selecao and r.selecao.regra not in ("sem_validacao",):
            L.append("  Ranking das metodologias testadas:")
            L += _tabela_ranking(r)
    L += ["", sep, "Fim do relatório.", ""]

    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text("\n".join(L), encoding=config.ENCODING_SAIDA)
    return caminho
