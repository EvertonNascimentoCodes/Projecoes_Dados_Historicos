# Projeção de Medições com Seleção Automática de Metodologia

Ferramenta desenvolvida em Python para **projeção mensal de medições de energia** (ou de qualquer grandeza com histórico mensal) a partir de um arquivo `DadosHistoricos.csv`, escolhendo **automaticamente, para cada medição, a metodologia de projeção mais aderente ao seu comportamento histórico**.

O projeto testa até 14 metodologias estatísticas para cada medição, valida cada uma delas com dados que já aconteceram (*backtesting*) e adota a de menor erro. Por isso, medições diferentes podem (e normalmente vão) usar metodologias diferentes. Ao final, gera os arquivos de projeção mensal e anual, as versões transpostas e um relatório em texto que justifica a escolha de cada medição.

## Funcionalidades

* Leitura do histórico em CSV UTF-8, separado por `;`, com decimal em `,` e validação completa: datas duplicadas, meses faltando na sequência, valores não numéricos e colunas inconsistentes;
* Identificação automática do **período ativo** de cada medição: descarta os zeros consecutivos do início (unidade ainda não ligada), trata blocos de zeros no meio e no final (unidade desligada) e descarta o mês de ligação parcial;
* Teste de **14 metodologias de projeção** por medição, de médias simples a Holt-Winters, método Theta, modelos autorregressivos e combinação de modelos;
* **Validação cruzada temporal** (*backtesting* com origem móvel) para medir o erro real de cada metodologia;
* **Verificação de plausibilidade** que descarta projeções negativas, não numéricas ou explosivas;
* **Critério de parcimônia**: em caso de empate técnico, prefere a metodologia mais simples;
* **Detecção de identidade contábil**: quando uma medição é a soma exata das demais (ex.: `MUX = PLASBIL + ... + LIQUIDA_MUX`), permite calcular a parcela líquida por diferença, garantindo que a soma das projeções feche com o total;
* **Modo retroativo**: se o início da projeção estiver dentro do histórico, usa apenas os dados anteriores e compara a projeção com o realizado no relatório;
* Geração de 4 arquivos CSV (mensal, anual e as duas versões transpostas) e de um **relatório TXT** com diagnóstico, ranking e justificativa de cada medição;
* Gravação opcional do resultado de **cada metodologia testada** para cada medição, em arquivos individuais;
* Execução interativa (perguntas no terminal) ou por parâmetros de linha de comando, para automação.

## Atenção para o correto preenchimento dos seguintes parâmetros

### Estrutura de pastas esperada

O `Master.py` deve ficar na **pasta raiz do projeto**, com o `DadosHistoricos.csv` ao lado dele:

```
meu_projeto/
├── Master.py
├── DadosHistoricos.csv                      (entrada)
├── requirements.txt
├── README.md
├── .gitignore
├── projecoes/                               (pacote com o código)
│   ├── config.py
│   ├── leitura.py
│   ├── datas.py
│   ├── preparacao.py
│   ├── diagnostico.py
│   ├── metodologias.py
│   ├── validacao.py
│   ├── consistencia.py
│   ├── motor.py
│   ├── exportacao.py
│   ├── relatorio.py
│   └── interface.py
├── tests/
│   └── test_projecoes.py
├── Projecoes_Resultados.csv                 (gerado)
├── Projecoes_Resultados_Anual.csv           (gerado)
├── Projecoes_Resultados_linhas.csv          (gerado)
├── Projecoes_Resultados_linhas_anos.csv     (gerado)
├── Relatorio_Metodologias.txt               (gerado)
└── Metodologias_Resultados/                 (gerado, opcional)
```

### Formato esperado do arquivo `DadosHistoricos.csv`

* Codificação **UTF-8** (com ou sem BOM);
* Separador de colunas **`;`** e separador decimal **`,`**;
* Primeira coluna chamada **`DATA`**, no formato `DD/MM/AAAA` (sempre o dia 01), com **um mês por linha e sem meses faltando**;
* Demais colunas: uma por medição, com o nome da medição no cabeçalho.

```
DATA;MUX;PLASBIL;PIETROBON;SIMONETTO;...;LIQUIDA_MUX
01/01/2021;6907,3200;795,5153;278,8983;0,0000;...;5832,9064
01/02/2021;5789,6307;772,5759;222,7945;0,0000;...;4794,2602
...
```

Medições com **zeros consecutivos** são tratadas como unidades ainda não ligadas (no início) ou desligadas (no final), e esses meses não entram no cálculo da projeção.

### Parâmetros informados interativamente ao executar o script

Ao rodar `python Master.py`, o script pergunta e valida, nesta ordem:

```
1) Mês/ano de INÍCIO da projeção (MM/AAAA)  -> Enter = mês seguinte ao último dado
2) Mês/ano de FIM da projeção (MM/AAAA)     -> deve ser igual ou posterior ao início
3) Medição calculada por diferença          -> só aparece se houver uma medição total igual à
   (identidade contábil)                       soma das demais; Enter = sugestão (ex.: LIQUIDA_MUX),
                                               N = nenhuma (todas projetadas de forma independente)
4) Gravar CSV de cada metodologia testada?  -> S ou N
```

Também é possível executar sem perguntas, informando tudo por parâmetros:

```
python Master.py --inicio 10/2026 --fim 12/2030 --identidade s --metodologias s
```

| Parâmetro | Descrição |
|---|---|
| `--arquivo` | Caminho do CSV de entrada (padrão: `DadosHistoricos.csv` na pasta do projeto) |
| `--saida` | Pasta onde os resultados serão gravados (padrão: pasta do projeto) |
| `--inicio` | Mês/ano inicial da projeção (`MM/AAAA`) |
| `--fim` | Mês/ano final da projeção (`MM/AAAA`) |
| `--identidade` | `s` (usa a sugestão), `n` (não aplica) ou o nome da medição calculada por diferença |
| `--metodologias` | `s` ou `n` para gravar os CSV de cada metodologia testada |

## Arquivos gerados

| Arquivo | Conteúdo |
|---|---|
| `Projecoes_Resultados.csv` | Projeção mês a mês, no mesmo layout do `DadosHistoricos.csv` |
| `Projecoes_Resultados_Anual.csv` | Total anual de cada medição (uma linha por ano) |
| `Projecoes_Resultados_linhas.csv` | Projeção mensal transposta: medições nas linhas, meses nas colunas |
| `Projecoes_Resultados_linhas_anos.csv` | Totais anuais transpostos: medições nas linhas, anos nas colunas |
| `Relatorio_Metodologias.txt` | Metodologia escolhida para cada medição, com justificativa, diagnóstico e ranking |
| `Metodologias_Resultados/[medicao]_[metodologia]_result.csv` | (opcional) projeção de cada metodologia testada, com as colunas `DATA` e nome da medição |

Todos os CSV usam `;` como separador, `,` como decimal, **4 casas decimais** e UTF-8. Os totais anuais são a **soma dos valores mensais já arredondados**, de modo que fecham exatamente com o arquivo mensal. Anos incompletos (ex.: projeção iniciando em outubro) somam apenas os meses projetados, e o relatório avisa quais anos estão nessa situação.

## Metodologias testadas

Cada medição passa por todas as metodologias abaixo. Algumas exigem um histórico mínimo e, quando a medição não tem meses suficientes, a metodologia aparece como **não elegível** no relatório. A **complexidade** é usada no critério de parcimônia (quanto menor, mais simples).

Nas fórmulas, `y` é a série histórica, `n` é a quantidade de meses do histórico ativo, `h` é o número de meses à frente e `ŷ` é o valor projetado.

### 1. Média Simples (`Media_Simples`)

* **Como funciona:** projeta um valor constante igual à média dos últimos 12 meses (ou de todos os meses, se houver menos de 12).
  `ŷ(n+h) = média(y[n-11] ... y[n])`
* **Quando é adequada:** séries estáveis, sem tendência nem sazonalidade relevantes, ou com poucos dados.
* **Histórico mínimo:** 1 mês | **Complexidade:** 1
* Também é a **metodologia de segurança**: é adotada quando há menos de 6 meses de histórico (sem validação possível) ou quando nenhuma outra passa nos critérios.

### 2. Média Móvel de 3 Meses (`Media_Movel_3M`)

* **Como funciona:** projeta um valor constante igual à média dos 3 últimos meses.
  `ŷ(n+h) = (y[n-2] + y[n-1] + y[n]) / 3`
* **Quando é adequada:** séries que mudam de patamar com frequência, em que o passado recente representa melhor o futuro do que a média do ano.
* **Histórico mínimo:** 3 meses | **Complexidade:** 1

### 3. Ingênuo Sazonal (`Naive_Sazonal`)

* **Como funciona:** repete o valor do mesmo mês do último ano disponível.
  `ŷ(n+h) = y[n + h - 12]` (repetindo o ciclo para horizontes maiores que 12)
* **Quando é adequada:** sazonalidade bem definida e estável, com nível que pouco varia de um ano para outro. Apesar de simples, costuma ser difícil de superar em séries fortemente sazonais.
* **Histórico mínimo:** 12 meses | **Complexidade:** 2

### 4. Suavização Exponencial Simples – SES (`Suavizacao_Exponencial_Simples`)

* **Como funciona:** estima o nível atual da série como uma média ponderada em que os meses mais recentes têm mais peso, com pesos decaindo exponencialmente. O parâmetro de suavização `α` (entre 0,01 e 0,99) é otimizado para minimizar o erro de ajuste.
  `nível(t) = α·y(t) + (1-α)·nível(t-1)` e `ŷ(n+h) = nível(n)`
* **Quando é adequada:** séries sem tendência nem sazonalidade, mas cujo nível oscila ao longo do tempo.
* **Histórico mínimo:** 4 meses | **Complexidade:** 2

### 5. Regressão Linear – Tendência (`Regressao_Linear`)

* **Como funciona:** ajusta uma reta por mínimos quadrados e a prolonga no futuro.
  `ŷ(t) = a + b·t`
* **Quando é adequada:** crescimento ou queda constante ao longo do tempo, sem sazonalidade relevante.
* **Histórico mínimo:** 4 meses (e pelo menos 24 meses para ser elegível, por extrapolar tendência) | **Complexidade:** 2

### 6. Média Sazonal (`Media_Sazonal`)

* **Como funciona:** calcula índices sazonais multiplicativos (quanto cada mês costuma ficar acima ou abaixo da média do ano, pela decomposição clássica com média móvel centrada 2×12) usando todo o histórico, e os aplica sobre o nível médio dos últimos 12 meses.
  `ŷ(n+h) = média(últimos 12 meses) × índice_sazonal(mês)`
* **Quando é adequada:** sazonalidade estável sem tendência. Gera um perfil sazonal mais suave que o ingênuo sazonal, pois usa a média de vários anos em vez de repetir um único ano.
* **Histórico mínimo:** 24 meses (valores positivos) | **Complexidade:** 3

### 7. Sazonal com Crescimento Anual (`Sazonal_Crescimento`)

* **Como funciona:** repete o perfil do último ano aplicando a taxa de crescimento anual observada (soma dos últimos 12 meses ÷ soma dos 12 anteriores), de forma composta a cada ano projetado.
  `g = Σ(últimos 12) / Σ(12 anteriores)` e `ŷ(n+h) = y[mesmo mês do último ano] × g^(ano à frente)`
* **Quando é adequada:** sazonalidade marcada com crescimento (ou queda) consistente ano a ano. É a abordagem mais usada informalmente em planilhas de projeção de consumo.
* **Histórico mínimo:** 24 meses | **Complexidade:** 3

### 8. Holt com Tendência Amortecida (`Holt_Amortecido`)

* **Como funciona:** suavização exponencial com duas componentes, nível e tendência, em que a tendência perde força ao longo do horizonte pelo fator de amortecimento `φ`. Os parâmetros `α` (nível), `β` (tendência) e `φ` (amortecimento, entre 0,80 e 0,98) são otimizados por mínimos quadrados.
  `ŷ(n+h) = nível(n) + (φ + φ² + ... + φʰ)·tendência(n)`
* **Quando é adequada:** séries com tendência, mas sem sazonalidade. O amortecimento evita que a tendência seja extrapolada indefinidamente, o que é mais realista em horizontes longos.
* **Histórico mínimo:** 6 meses (e pelo menos 24 meses para ser elegível, por extrapolar tendência) | **Complexidade:** 4

### 9. Método Theta (`Theta`)

* **Como funciona:** método clássico de Assimakopoulos & Nikolopoulos (2000), na formulação de Hyndman & Billah. Quando a sazonalidade é estatisticamente significativa (teste de autocorrelação no lag 12, com 90% de confiança), a série é dessazonalizada antes. Depois combina uma suavização exponencial simples com **metade da inclinação** da tendência linear e, por fim, reaplica a sazonalidade.
  `ŷ(n+h) = SES(n) + ½·b·(h - 1 + (1 - (1-α)ⁿ)/α)`
* **Quando é adequada:** método robusto, de uso geral, e vencedor da competição internacional de previsão M3. Funciona bem em séries com tendência moderada.
* **Histórico mínimo:** 4 meses (e pelo menos 24 meses para ser elegível, por extrapolar tendência) | **Complexidade:** 4

### 10. Regressão Linear com Sazonalidade Mensal (`Regressao_Linear_Sazonal`)

* **Como funciona:** regressão por mínimos quadrados com uma tendência linear e um efeito fixo (variável indicadora) para cada mês do ano.
  `ŷ(t) = a + b·t + efeito(mês de t)`
* **Quando é adequada:** tendência constante com sazonalidade estável e amplitude sazonal que não muda com o nível.
* **Histórico mínimo:** 24 meses | **Complexidade:** 5

### 11. Autorregressivo Sazonal – AR(1, 12) (`Autoregressivo_Sazonal`)

* **Como funciona:** explica o valor de cada mês pelo mês anterior (inércia) e pelo mesmo mês do ano anterior (sazonalidade), com coeficientes estimados por mínimos quadrados. A projeção é recursiva: cada mês projetado serve de entrada para o seguinte. Modelos explosivos (`|a₁| + |a₁₂| ≥ 1`) são rejeitados automaticamente.
  `ŷ(t) = c + a₁·y(t-1) + a₁₂·y(t-12)`
* **Quando é adequada:** séries com forte dependência do passado recente e sazonalidade.
* **Histórico mínimo:** 36 meses | **Complexidade:** 5

### 12. Holt-Winters Aditivo com Tendência Amortecida (`HoltWinters_Aditivo`)

* **Como funciona:** suavização exponencial com três componentes (nível, tendência amortecida e sazonalidade) em que a sazonalidade é **somada** ao nível. Os parâmetros `α`, `β`, `γ` (sazonalidade) e `φ` são otimizados por mínimos quadrados, com várias tentativas de ponto de partida para evitar mínimos locais. O estado inicial é obtido dos dois primeiros anos, já descontando a tendência dos fatores sazonais.
  `ŷ(n+h) = nível(n) + (φ + ... + φʰ)·tendência(n) + sazonal(mês)`
* **Quando é adequada:** tendência e sazonalidade com **amplitude sazonal constante** (a diferença entre meses altos e baixos não cresce com o nível).
* **Histórico mínimo:** 24 meses | **Complexidade:** 6

### 13. Holt-Winters Multiplicativo com Tendência Amortecida (`HoltWinters_Multiplicativo`)

* **Como funciona:** igual ao anterior, mas a sazonalidade **multiplica** o nível.
  `ŷ(n+h) = [nível(n) + (φ + ... + φʰ)·tendência(n)] × sazonal(mês)`
* **Quando é adequada:** tendência e sazonalidade com **amplitude sazonal proporcional ao nível** (quando o consumo cresce, a diferença entre meses altos e baixos cresce junto).
* **Histórico mínimo:** 24 meses (apenas valores positivos) | **Complexidade:** 6

### 14. Combinação de Modelos (`Combinacao_Modelos`)

* **Como funciona:** média aritmética, mês a mês, das projeções dos modelos estruturais que foram aprovados para aquela medição: Theta, Holt amortecido, Holt-Winters aditivo e multiplicativo, regressão sazonal, autorregressivo sazonal e sazonal com crescimento. A combinação é validada da mesma forma que os demais métodos.
* **Quando é adequada:** quando nenhum modelo isolado domina. A literatura de previsão mostra que combinar modelos costuma reduzir o erro, pois os erros individuais tendem a se compensar.
* **Histórico mínimo:** pelo menos 2 modelos estruturais válidos | **Complexidade:** 7

## Como a melhor metodologia é escolhida

1. **Período ativo:** para cada medição, o script isola o trecho em que a unidade está efetivamente ligada (veja *Decisões de projeto adotadas*).
2. **Validação cruzada temporal (backtesting):** o script "volta no tempo" e, em até **4 janelas**, treina cada metodologia apenas com os dados anteriores à janela e projeta os meses seguintes (até **12 meses**; em séries curtas, `n ÷ 4` meses). A projeção é comparada com o que realmente aconteceu.
3. **Métrica de erro – WAPE** (*Weighted Absolute Percentage Error*):
   `WAPE = Σ|projetado - real| / Σ|real|`
   Indica quanto a projeção errou em relação ao volume total. Os meses de maior consumo pesam mais, o que é o mais adequado para energia. O relatório também mostra o **viés** (`Σ(projetado - real) / Σ|real|`): positivo indica que o método costuma projetar acima do real e negativo, abaixo.
4. **Plausibilidade:** a projeção final de cada metodologia é reprovada se tiver valores negativos ou não numéricos, se a média dos 12 primeiros meses projetados ficar fora de 0,5× a 2× a média dos últimos 12 meses reais, ou se a média dos 12 últimos meses projetados ficar fora de 0,33× a 3× (extrapolação explosiva).
5. **Parcimônia:** entre as metodologias aprovadas cujo WAPE esteja até **2% (relativo)** acima do melhor, é escolhida a de menor complexidade, pois modelos mais simples tendem a ser mais estáveis em horizontes longos.

Todos esses limites podem ser ajustados em `projecoes/config.py`.

## Decisões de projeto adotadas

* **Zeros iniciais** de uma medição indicam unidade ainda não ligada e são descartados.
* **Blocos internos com 2 ou mais zeros consecutivos** indicam desligamento temporário: é usado apenas o período ativo mais recente, após o último bloco de zeros.
* **2 ou mais zeros consecutivos no final** indicam unidade desligada: a projeção é zero.
* Um **zero isolado** dentro do período ativo é mantido e sinalizado no relatório para conferência (pode ser falha de medição).
* **Mês de ligação parcial:** se o primeiro mês após a ligação for inferior a 30% da mediana dos 6 meses seguintes, é descartado (ex.: unidade ligada no fim do mês).
* **Células vazias** dentro do período ativo são preenchidas por interpolação linear e informadas no relatório.
* **Métodos que extrapolam tendência** (regressões, Holt, Theta, Holt-Winters, autorregressivo e sazonal com crescimento) só são elegíveis com pelo menos **24 meses** de histórico ativo. Com menos de 2 anos não é possível separar tendência de sazonalidade ou da rampa de ligação, e extrapolar por vários anos seria arriscado.
* **Força sazonal** (diagnóstico do relatório) só é calculada com pelo menos 36 meses, para não gerar valores artificiais.
* **Identidade contábil:** quando uma medição é a soma exata de todas as demais em todo o histórico, a parcela escolhida pelo usuário é calculada como `total - demais parcelas` sobre as projeções. A projeção independente dessa parcela continua no ranking do relatório como referência.
* **Modo retroativo:** se o início da projeção estiver dentro do histórico, os modelos usam apenas os dados anteriores ao início, e o relatório mostra o WAPE da projeção contra o realizado.
* **Meses intermediários:** se o início pedido for posterior ao mês seguinte ao último dado, os meses intermediários são projetados internamente, mas não são gravados.
* Todas as metodologias foram implementadas no próprio projeto com `numpy` e `scipy`, sem bibliotecas de previsão de terceiros, para que os cálculos sejam transparentes, auditáveis e determinísticos (a mesma entrada gera sempre a mesma saída).
* A pasta `Metodologias_Resultados` é limpa (apenas os arquivos `*_result.csv`) a cada nova gravação, para não misturar resultados de execuções diferentes.

### Tecnologias utilizadas

* **Python 3.13** (testado no Python 3.13.16; requer 3.10 ou superior)
* **NumPy** (testado na versão 2.5.3): cálculos vetoriais e regressões por mínimos quadrados
* **SciPy** (testado na versão 1.18.1): otimização dos parâmetros das suavizações exponenciais e testes estatísticos de tendência

Bibliotecas nativas do Python, como `csv`, `argparse`, `dataclasses`, `datetime`, `pathlib` e `re`, também são utilizadas no projeto.

## Testes automatizados

O projeto inclui 16 testes automatizados que cobrem leitura do CSV, tratamento de zeros, mês de ligação parcial, metodologias, seleção, identidade contábil e modo retroativo. Para executá-los, na pasta do projeto:

```
python -m unittest discover -s tests -v
```

## Objetivo

O objetivo do projeto é substituir projeções feitas manualmente, ou com uma única metodologia aplicada a todas as medições, por um processo **padronizado, auditável e estatisticamente fundamentado**, em que cada medição recebe a metodologia que melhor representa seu próprio comportamento histórico.

O projeto pode ser utilizado como base para estudos relacionados a:

* Projeção de consumo e demanda de energia de unidades consumidoras;
* Planejamento de contratos de energia e orçamento;
* Balanço energético entre medição total e medições individuais;
* Avaliação comparativa de metodologias de previsão de séries temporais.

## Comandos gerais úteis para seu venv no VSCode

Antes de criar o ambiente, vale conferir se essa é realmente a pasta onde está seu `Master.py`. No VS Code, execute: `dir`

Se aparecer `Master.py`, podemos criar o ambiente aí mesmo: `py -3.13 -m venv .venv`

Ativando ambiente no PowerShell do VS Code: `.\.venv\Scripts\Activate.ps1`

Atualizando pip: `python -m pip install --upgrade pip`

Instalando as dependências do projeto: `pip install -r requirements.txt`

Conferindo o que foi instalado: `pip list`

Executando o script: `python Master.py`

Executando os testes: `python -m unittest discover -s tests -v`

## Status do projeto

🚧 **Em desenvolvimento**

Novas funcionalidades e melhorias serão adicionadas ao projeto ao longo do desenvolvimento.

## Licença

Este projeto é disponibilizado sob licença própria.

O uso não comercial é permitido, desde que seja mantida a atribuição ao autor.

O uso comercial, redistribuição comercial ou incorporação do código em produtos ou serviços comerciais está sujeito às condições estabelecidas na licença do projeto.

Consulte o arquivo `LICENSE` para obter os termos completos.

## Autor

**Everton Nascimento**

Electrical Engineer | Energy Systems | Physics & Engineering Education | Technology Solutions & Data Analytics

---

*Projeto desenvolvido para automação e apoio à projeção de medições de energia com seleção estatística de metodologia.*
