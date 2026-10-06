"""
Configurações centrais do projeto de projeção de medições.

Todos os parâmetros que influenciam leitura, escrita, validação e escolha
das metodologias ficam aqui, para que possam ser ajustados sem mexer na
lógica do programa.
"""

# --------------------------------------------------------------------------
# Arquivos de entrada / saída
# --------------------------------------------------------------------------
ARQUIVO_ENTRADA_PADRAO = "DadosHistoricos.csv"

ARQ_MENSAL = "Projecoes_Resultados.csv"
ARQ_ANUAL = "Projecoes_Resultados_Anual.csv"
ARQ_LINHAS = "Projecoes_Resultados_linhas.csv"
ARQ_LINHAS_ANOS = "Projecoes_Resultados_linhas_anos.csv"
ARQ_RELATORIO = "Relatorio_Metodologias.txt"
PASTA_METODOLOGIAS = "Metodologias_Resultados"

# --------------------------------------------------------------------------
# Formato dos arquivos CSV
# --------------------------------------------------------------------------
SEPARADOR = ";"
SEPARADOR_DECIMAL = ","
ENCODING_ENTRADA = "utf-8-sig"   # lê UTF-8 com ou sem BOM
ENCODING_SAIDA = "utf-8"
CASAS_DECIMAIS = 4
FORMATO_DATA = "%d/%m/%Y"
COLUNA_DATA = "DATA"
COLUNA_ANO = "ANO"
COLUNA_MEDICAO = "MEDICAO"

# --------------------------------------------------------------------------
# Tratamento da série histórica
# --------------------------------------------------------------------------
PERIODO_SAZONAL = 12            # dados mensais -> ciclo anual
MIN_ZEROS_CONSECUTIVOS = 2      # zeros seguidos que caracterizam "desligada"
LIMIAR_MES_PARCIAL = 0.30       # 1º mês após a ligação < 30% da mediana
                                # dos meses seguintes => mês de ligação parcial

# --------------------------------------------------------------------------
# Validação cruzada temporal (rolling origin / backtesting)
# --------------------------------------------------------------------------
CV_HORIZONTE_MAX = 12           # horizonte de teste máximo (meses)
CV_MAX_DOBRAS = 4               # número máximo de janelas de teste
CV_MIN_TREINO = 4               # menor tamanho de treino admitido
N_MIN_VALIDACAO = 6             # abaixo disso não há validação possível

# Métodos que extrapolam tendência só são elegíveis com ao menos este número
# de meses ativos: com menos de 2 anos não se distingue tendência de
# sazonalidade/rampa de ligação, e extrapolar por anos seria arriscado.
MIN_MESES_TENDENCIA = 24

# Parcimônia: entre os métodos cujo erro esteja até X% (relativo) acima do
# melhor, escolhe-se o de menor complexidade (reduz risco de sobreajuste).
TOLERANCIA_PARCIMONIA = 0.02

# Verificação de plausibilidade da projeção final (razão entre a média
# projetada e a média dos últimos 12 meses históricos).
PLAUS_RAZAO_PRIMEIROS_12 = (0.50, 2.00)
PLAUS_RAZAO_ULTIMOS_12 = (0.33, 3.00)

# Identidade entre medições (ex.: LIQUIDA = TOTAL - soma das demais)
TOL_IDENTIDADE_ABS = 0.01       # tolerância absoluta por mês
TOL_IDENTIDADE_REL = 1e-6       # tolerância relativa ao valor da base

# Horizonte acima do qual o programa alerta sobre incerteza elevada
ALERTA_HORIZONTE_MESES = 60
