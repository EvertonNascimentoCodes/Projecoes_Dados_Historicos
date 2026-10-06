#!/usr/bin/env python3
"""
Master.py - Ponto de entrada do sistema de projeção de medições.

Uso interativo (pergunta tudo no terminal):
    python Master.py

Uso por parâmetros (sem perguntas; útil para automatizar):
    python Master.py --inicio 10/2026 --fim 12/2030 --metodologias s --identidade s

Fluxo:
  1. Lê DadosHistoricos.csv (UTF-8, ';' como separador, ',' como decimal).
  2. Pergunta o mês/ano inicial e final da projeção.
  3. Para cada medição: identifica o período ativo (descarta zeros de unidade
     não ligada), testa todas as metodologias por validação cruzada temporal e
     escolhe a mais aderente.
  4. Grava Projecoes_Resultados.csv, Projecoes_Resultados_Anual.csv,
     Projecoes_Resultados_linhas.csv, Projecoes_Resultados_linhas_anos.csv e
     Relatorio_Metodologias.txt.
  5. Pergunta se deve gravar os resultados de cada metodologia testada em
     Metodologias_Resultados/[medicao]_[metodologia]_result.csv.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from projecoes import __version__, config
from projecoes.consistencia import criar_identidade, detectar_totais
from projecoes.datas import formatar_mes_ano, indice_mes, interpretar_mes_ano, somar_meses
from projecoes.exportacao import gravar_metodologias, gravar_resultados
from projecoes.interface import (converter_sim_nao, perguntar_derivada, perguntar_mes_ano,
                                 perguntar_sim_nao)
from projecoes.leitura import ErroLeitura, ler_dados_historicos
from projecoes.metodologias import POR_NOME
from projecoes.motor import (METODO_IDENTIDADE, aplicar_identidades, definir_parametros,
                             projetar_todas)
from projecoes.relatorio import gerar_relatorio

PASTA_PROJETO = Path(__file__).resolve().parent


def _args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Projeção de medições mensais com seleção automática "
                                            "da melhor metodologia por medição.")
    p.add_argument("--arquivo", help=f"CSV de entrada (padrão: {config.ARQUIVO_ENTRADA_PADRAO} na pasta do projeto)")
    p.add_argument("--saida", help="Pasta de saída (padrão: pasta do projeto)")
    p.add_argument("--inicio", help="Mês/ano inicial da projeção (MM/AAAA)")
    p.add_argument("--fim", help="Mês/ano final da projeção (MM/AAAA)")
    p.add_argument("--identidade", help="Identidade total = soma das parcelas: s (usa a sugestão), "
                   "n (não aplica) ou o nome da medição calculada por diferença")
    p.add_argument("--metodologias", help="Gravar CSV de cada metodologia testada? (s/n)")
    return p.parse_args()


def _localizar_arquivo(args) -> Path:
    if args.arquivo:
        return Path(args.arquivo).expanduser().resolve()
    padrao = PASTA_PROJETO / config.ARQUIVO_ENTRADA_PADRAO
    if padrao.is_file():
        return padrao
    print(f"Arquivo '{config.ARQUIVO_ENTRADA_PADRAO}' não encontrado em {PASTA_PROJETO}.")
    while True:
        caminho = Path(input("Informe o caminho completo do arquivo CSV: ").strip().strip('"')).expanduser()
        if caminho.is_file():
            return caminho.resolve()
        print("  ! Arquivo não encontrado.")


def _progresso(k: int, total: int, nome: str) -> None:
    print(f"  [{k:>2}/{total}] {nome:<25}", end="\r", flush=True)


def main() -> int:
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(errors="replace")
        except AttributeError:
            pass
    args = _args()
    print("=" * 78)
    print(f" PROJEÇÃO DE MEDIÇÕES  -  seleção automática de metodologia  (v{__version__})")
    print("=" * 78)

    # 1. Leitura ---------------------------------------------------------------
    arquivo = _localizar_arquivo(args)
    try:
        dados = ler_dados_historicos(arquivo)
    except ErroLeitura as exc:
        print(f"\nERRO ao ler o arquivo: {exc}")
        return 1
    pasta_saida = Path(args.saida).expanduser().resolve() if args.saida else PASTA_PROJETO

    print(f"\nArquivo lido: {arquivo.name}")
    print(f"  Histórico : {formatar_mes_ano(dados.primeira_data)} a {formatar_mes_ano(dados.ultima_data)} "
          f"({len(dados.datas)} meses)")
    print(f"  Medições  : {len(dados.medicoes)} -> {', '.join(dados.medicoes)}")
    for a in dados.avisos:
        print(f"  AVISO: {a}")

    # 2. Período da projeção ---------------------------------------------------
    sugestao = somar_meses(dados.ultima_data, 1)
    minimo = somar_meses(dados.primeira_data, 1)
    print()
    try:
        inicio = interpretar_mes_ano(args.inicio) if args.inicio else \
            perguntar_mes_ano("Mês/ano de INÍCIO da projeção (MM/AAAA)", sugestao, minimo)
        fim = interpretar_mes_ano(args.fim) if args.fim else \
            perguntar_mes_ano("Mês/ano de FIM da projeção (MM/AAAA)", None, inicio)
        params = definir_parametros(dados, inicio, fim)
    except ValueError as exc:
        print(f"\nERRO: {exc}")
        return 1

    avisos_gerais = list(dados.avisos)
    if indice_mes(inicio) <= indice_mes(dados.ultima_data):
        msg = (f"O início ({formatar_mes_ano(inicio)}) está dentro do histórico: os modelos usarão somente "
               f"dados até {formatar_mes_ano(params.fim_treino)} (modo de teste retroativo). O relatório "
               "compara a projeção com o realizado nos meses sobrepostos.")
        print(f"  AVISO: {msg}")
        avisos_gerais.append(msg)
    if indice_mes(inicio) > indice_mes(sugestao):
        msg = (f"Há {params.deslocamento_saida} mês(es) entre o fim do histórico e o início pedido; eles "
               "são projetados internamente, mas não são gravados.")
        print(f"  AVISO: {msg}")
        avisos_gerais.append(msg)
    if params.horizonte > config.ALERTA_HORIZONTE_MESES:
        msg = (f"Horizonte de {params.horizonte} meses à frente do último dado: a incerteza cresce com o "
               "horizonte; recomenda-se revisar as projeções periodicamente.")
        print(f"  AVISO: {msg}")
        avisos_gerais.append(msg)

    # 3. Identidades entre medições -------------------------------------------
    n_treino = indice_mes(params.fim_treino) - indice_mes(dados.primeira_data) + 1
    totais = detectar_totais(dados.medicoes, {m: dados.valores[m][:n_treino] for m in dados.medicoes})
    aplicar = []
    for total in totais:
        sugestao_der = total.sugestao_derivada()
        erro_txt = f"{total.erro_max:.4f}".replace(".", ",")
        print(f"\nIdentidade detectada em todo o histórico (diferença máxima {erro_txt}):\n"
              f"  {total.base} = soma de todas as demais medições")
        if args.identidade:
            resp = args.identidade.strip()
            derivada = None if resp.lower() in ("n", "nao", "não", "no") else (
                sugestao_der if resp.lower() in ("s", "sim", "y", "yes") else resp)
        else:
            print(f"  Uma das parcelas pode ser calculada por diferença ({total.base} - demais), "
                  "garantindo que a soma projetada feche com o total.")
            derivada = perguntar_derivada(total.parcelas, sugestao_der)
        if derivada:
            try:
                ident = criar_identidade(total, derivada)
            except ValueError as exc:
                print(f"\nERRO: {exc}")
                return 1
            aplicar.append(ident)
            print(f"  -> {ident.derivada} será calculada por: {ident.base} - (demais medições)")
        else:
            avisos_gerais.append(f"Identidade detectada mas NÃO aplicada (opção do usuário): "
                                 f"{total.descricao()}. Todas as medições foram projetadas de forma "
                                 "independente; a soma das parcelas pode não fechar com o total.")

    # 4. Projeção ---------------------------------------------------------------
    print(f"\nProjetando {formatar_mes_ano(inicio)} a {formatar_mes_ano(fim)} "
          f"(ajuste com dados até {formatar_mes_ano(params.fim_treino)})...")
    t0 = time.time()
    resultados = projetar_todas(dados, params, _progresso)
    aplicar_identidades(resultados, aplicar)
    print(" " * 60, end="\r")
    print(f"  Concluído em {time.time() - t0:.1f} s.")

    # 5. Gravação ---------------------------------------------------------------
    ini, fim_idx = params.deslocamento_saida, params.deslocamento_saida + len(params.datas_saida)
    proj_saida = {m: resultados[m].projecao[ini:fim_idx] for m in dados.medicoes}
    try:
        arquivos = gravar_resultados(pasta_saida, params.datas_saida, dados.medicoes, proj_saida)
        arquivos.append(gerar_relatorio(pasta_saida / config.ARQ_RELATORIO, arquivo, dados, params,
                                        resultados, avisos_gerais))
    except PermissionError as exc:
        print(f"\nERRO: não foi possível gravar ({exc}). Feche os arquivos abertos (ex.: no Excel) e "
              "execute novamente.")
        return 1

    print("\nMetodologia escolhida por medição:")
    for m in dados.medicoes:
        r = resultados[m]
        nome = r.metodo_final
        titulo = POR_NOME[nome].titulo if nome in POR_NOME else (
            f"Identidade ({r.identidade.base} - demais)" if nome == METODO_IDENTIDADE else nome)
        wape = ""
        if r.selecao and nome in r.selecao.resultados:
            w = r.selecao.resultados[nome].wape
            if w == w:
                wape = f"WAPE {w * 100:.2f}%".replace(".", ",")
        print(f"  {m:<20} {titulo:<52} {wape}")

    print("\nArquivos gerados:")
    for a in arquivos:
        print(f"  - {a}")

    # 6. Resultados individuais por metodologia ---------------------------------
    print()
    if args.metodologias:
        gravar = converter_sim_nao(args.metodologias)
    else:
        gravar = perguntar_sim_nao("Deseja criar os CSV de cada metodologia testada para cada medição "
                                   f"(pasta {config.PASTA_METODOLOGIAS})?", False)
    if gravar:
        series = []
        for m in dados.medicoes:
            r = resultados[m]
            if r.selecao:
                for res in r.selecao.ranking():
                    if res.previsao_final is not None:
                        series.append((m, res.nome, res.previsao_final[ini:fim_idx]))
            if r.metodo_final == METODO_IDENTIDADE:
                series.append((m, METODO_IDENTIDADE, r.projecao[ini:fim_idx]))
        try:
            gerados = gravar_metodologias(pasta_saida, params.datas_saida, series)
        except PermissionError as exc:
            print(f"ERRO: não foi possível gravar ({exc}).")
            return 1
        print(f"  {len(gerados)} arquivo(s) gravado(s) em {pasta_saida / config.PASTA_METODOLOGIAS}")
    else:
        print("  Arquivos individuais de metodologia não foram gerados.")

    print("\nProcesso finalizado com sucesso.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nExecução cancelada pelo usuário.")
        sys.exit(130)
