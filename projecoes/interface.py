"""Interação com o usuário no terminal."""

from __future__ import annotations

from datetime import date

from .datas import formatar_mes_ano, interpretar_mes_ano, indice_mes


def perguntar_mes_ano(mensagem: str, padrao: date | None = None, minimo: date | None = None) -> date:
    sufixo = f" [Enter = {formatar_mes_ano(padrao)}]" if padrao else ""
    while True:
        resp = input(f"{mensagem}{sufixo}: ").strip()
        if not resp and padrao:
            return padrao
        try:
            d = interpretar_mes_ano(resp)
        except ValueError as exc:
            print(f"  ! {exc}")
            continue
        if minimo and indice_mes(d) < indice_mes(minimo):
            print(f"  ! O mês deve ser igual ou posterior a {formatar_mes_ano(minimo)}.")
            continue
        return d


def perguntar_sim_nao(mensagem: str, padrao: bool | None = None) -> bool:
    opcoes = "[S/n]" if padrao is True else "[s/N]" if padrao is False else "[s/n]"
    while True:
        resp = input(f"{mensagem} {opcoes}: ").strip().lower()
        if not resp and padrao is not None:
            return padrao
        if resp in ("s", "sim", "y", "yes"):
            return True
        if resp in ("n", "nao", "não", "no"):
            return False
        print("  ! Responda S (sim) ou N (não).")


def perguntar_derivada(parcelas: list[str], sugestao: str) -> str | None:
    """Pergunta qual parcela é calculada por diferença. Retorna None para não aplicar."""
    while True:
        resp = input(f"  Qual medição é calculada por diferença? [Enter = {sugestao} | N = nenhuma]: ").strip()
        if not resp:
            return sugestao
        if resp.lower() in ("n", "nao", "não", "nenhuma"):
            return None
        for p in parcelas:
            if p.upper() == resp.upper():
                return p
        print(f"  ! Informe uma destas: {', '.join(parcelas)}")


def converter_sim_nao(texto: str) -> bool:
    t = texto.strip().lower()
    if t in ("s", "sim", "y", "yes", "1", "true"):
        return True
    if t in ("n", "nao", "não", "no", "0", "false"):
        return False
    raise ValueError(f"Valor inválido '{texto}': use s ou n.")
