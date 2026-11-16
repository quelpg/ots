# TODO

## Perguntas da metodologia (pra não fugir do ponto)

**Pergunta central:** abrir linhas de forma planejada (OTS) reduz o custo de operação e o
congestionamento de um sistema que precisa ser seguro N-1? Em que situações vale a pena?

**Hipótese:** o ganho é pequeno quando geração e carga estão bem distribuídas, e maior quando a
geração barata está longe da carga (a energia precisa atravessar a rede).

| # | Pergunta | O que quero mostrar | Métricas | Não é o objetivo |
|---|---|---|---|---|
| 1 | Quanto custa a segurança N-1 sem chaveamento? (SC-DCOPF, K = 0) | O "prêmio de segurança", que é o custo que o OTS tenta recuperar | Custo sem N-1 x com N-1 (93.152 → 109.681 $/h, +17,7%); contingências que tornam o problema inviável | Viabilizar as 3 contingências excluídas (isso é a B) |
| A | Quanto o OTS reduz esse custo, e com quantas linhas abertas? | Curva custo x K: joelho e saturação | Custo, economia %, linhas abertas, % do prêmio de segurança recuperado | Provar otimalidade para K ≥ 3 (reportar "melhor encontrada, gap ~7%" e explicar o big-M) |
| A+ | As soluções de A são boas o bastante? Por que o OTS abre essas linhas? | Que os resultados são confiáveis e qual é o mecanismo (onde está o gargalo e como ele muda com K) | Custo melhorado por K; ranking das contingências limitantes (duais) | Virar um projeto de algoritmo (a busca local é ferramenta, não contribuição) |
| V | As soluções do OTS estão corretas fisicamente? | Que a topologia com as linhas abertas atende ao N-1 num fluxo independente | pandapower por estado (como os 194/194 do SC-DCOPF); ilhas, se houver | AC-OPF ou análise de tensão |
| B | Com todas as contingências (C_T completo), o OTS torna o problema viável? Com quantas aberturas? | Que o chaveamento também serve para viabilizar a segurança, não só para reduzir custo | K mínimo viável; custo em K_min, K_min + 1, ... | Uma nova sweep completa de K = 0 a 10 |
| R | A localização da renovável muda o valor do OTS? | O teste direto da hipótese: concentrada → mais congestionamento, curtailment e ganho do OTS; distribuída → pouco ganho | Custo, curtailment, contingências limitantes | Modelar incerteza ou estocasticidade das renováveis |

**Antes de começar qualquer tarefa:**
1. Qual pergunta (1, A, A+, V, B, R) isso ajuda a responder?
2. Que número ou gráfico vai para a tese por causa disso?
3. Se nenhuma das duas respostas for clara, deixar para o fim ou descartar.

Os resultados e a interpretação de cada análise ficam em `RESULTS_NOTES.md` (§0 tem o mapa das
análises). O mapa caso de estudo → pasta e os comandos estão no `README.md`.

**Reorganização de 2026-11-16:** o projeto foi organizado por caso de estudo (`reference/`,
`cs1-cost/`, `cs2-feasibility/`, `cs3-renewables/`, `heuristics/`, `preprocessing/`). O código antigo foi para
`old/pre-reorg-2026-11/` (tag git `pre-reorg`); os caminhos de código citados nos itens já feitos
abaixo se referem a ele.

---

## Reorganização e reescrita do código em `.py` (2026-11-16)

- [x] Parte 1: mover as pastas (commit só de renomeações), READMEs, caminhos do pré-processamento
      (rodado de novo: `processed/` e o diagrama não mudaram)
- [x] Parte 2: pacote `model/` (`data.py`, `states.py`, `build.py`, `solution.py`, `run_ots.py`) +
      `tests/check_reference.py` (21/21): reproduz 109.681,25 / 107.665,95, o custo salvo de todas as
      topologias K0..K10, a grade de λ e λ_max = 0,8501; CSVs idênticos aos do notebook (K2).
      Objetivos: custo, max λ, chaveamento mínimo (K_min). Força bruta K = 1 confirma o ótimo do MILP
- [ ] Portar a heurística (`heuristics/ranking_test.py`) para o pacote
- [ ] Texto: o limite de ângulo de ±0,6 rad fica ativo em cargas menores mesmo sem limite térmico
      (custo da rede sem limite térmico > despacho sem rede em até 30 $/h em λ = 0,85)
- [ ] Reescrever os scripts de cada caso usando o pacote (sweep de K, figura, core screening), cada um
      reproduzindo o resultado antigo
- [ ] `validation/`: `common.py` + um `validate_<caso>.py` por caso de estudo
- [ ] Todo script com `--help` completo e listado no README da pasta

---

## IEEE 118 barras - caso base

- [x] **1** - SC-DCOPF com a formulação revisada (custo só do caso base, F^em = 1,15 F^max,
      acoplamento preventivo, fatores de participação alpha, theta em ±0,6 rad)
- [x] Análise de vulnerabilidade (Seção 10 de `sc-dcopf/sc-dcopf.ipynb`).
      Exclusões: linha 8-5 (sozinha), linha 38-65 e gerador da barra 10 (em conjunto)
- [x] Validação do SC-DCOPF com pandapower, a posteriori (194/194 estados passam)
- [x] OTS-SC-DCOPF com a formulação revisada (K = 0 reproduz o SC-DCOPF)
- [ ] Atualizar o texto da tese: as exclusões são 8-5 (sozinha), **38-65** e gerador da barra 10
      (conjuntas). O 38-37 era do modelo antigo (corretivo, sem F^em)
- [ ] Revisar as notas marcadas com `% [REVISAR]` em `metodologia tcc.txt`

### Análise A - sweep de K (`redispatch_with_exclusions`)

- [x] Sweep K = 0..10 no cluster (3 threads, até 6 h por K)
- [x] Nova rodada local de K = 3..10 com warm start encadeado (cada K parte do melhor resultado com
      K' ≤ K), o que corrigiu os custos não monotônicos do cluster. Logs em `ots-sc-dcopf/logs/`
- [x] Custo x K comparado com o SC-DCOPF (109.681,25 $/h): o OTS recupera de 12,2% (K = 2) a
      17,5% (K = 8) do prêmio de segurança (+16.529 $/h)
- [x] Gráfico: `ots-sc-dcopf/plot_k_sweep.py` → `figures/k_sweep_redispatch_with_exclusions_contingencies.png`
- [ ] Quais linhas abrem, se elas se repetem entre os K e quais limites elas aliviam
      (já se sabe: as soluções são aninhadas de K1 até K8)
- [ ] Mudanças no despacho (quais geradores ganham e quais perdem)

### NOVA ESTRUTURA DOS CASOS (2026-11-16) – prevalece sobre o que está abaixo

- Lista **completa** (197 estados = 1 + 177 linhas não radiais + 19 geradores; os outros 35 dos 54
  do MATPOWER são compensadores síncronos, Pmax = 0) em todos os casos, sem exclusões; varia o
  nível de carga **λ** (todas as cargas × λ; a geração não escala). K continua sendo o nº máximo de
  linhas abertas.
- [x] Teste de λ reproduzido no PC com Gurobi (mesmos custos da nuvem): completa viável até
      λ_max = 0,8501 (3.606 MW); reduzida até 1,0099; DCOPF sem N-1 até 1,33
- [x] A inviabilidade acima de λ_max é da rede: nenhuma contingência é inviável sozinha; o conflito
      mínimo em λ = 0,852 é base + linha 8-5 + linha 26-30 + gerador da barra 10 + gerador da barra 66
      (tirando qualquer um, fica viável). Sem a maior unidade (1.182 MW) ainda sobram 5.333 MW
- [ ] Parâmetro λ (`load_factor`) e lista completa como padrão no pacote `model/`
- [ ] Referência: grade de λ (0,50 … 0,85): despacho sem restrição de rede, DCOPF, SC-DCOPF, prêmio de segurança
- [ ] CS1 (custo, λ ≤ λ_max): heurística em todos os λ da grade; MILP com warm start em 2–3 λ
      escolhidos pela grade
- [ ] CS2 (recuperar a viabilidade, λ > λ_max; ex.: 0,90 / 0,95 / 1,0): LP relaxado (folgas nos
      limites de fluxo, min violação) → heurística com os duais desse LP até a violação zerar (K_h,
      viabilidade provada pelo LP sem folgas) → MILP de chaveamento mínimo com warm start (K menor e
      limite inferior) → MILP de custo nesse K. Resultado: K_min por λ. Em λ = 1, K ≤ 3 já é inviável
- [ ] Ferramenta auxiliar: LP de max λ (carga máxima que uma topologia fixa aguenta sob N-1)
- [ ] CS3 (renováveis): λ ≈ 0,80, concentrado × distribuído
- A varredura antiga (λ = 1, lista reduzida) vira só validação da heurística
  (`heuristics/benchmark/`). O "CS1b" (aumentar a carga com a lista reduzida) foi descartado.

### Heurística sequencial (2026-11-15; portada para o pacote em 2026-11-16)

- [x] Teste da heurística do Ruiz (Fig. 1) com os critérios LP0, LP, PD, PW, TD (15/11, HiGHS)
- [x] Portada para o pacote: `heuristics/sequential.py` (duais do `OTSModel`, PTDF por estado com
      atualização por LODF, não abre linha que ilha o caso base, exporta as topologias para warm start)
- [x] Conferida no PC com Gurobi: mesmos critérios (1e-8) e mesmos caminhos do teste de 15/11
- [x] K = 6 (77-80, 89-92, 64-65, 68-69, 103-105, 103-104) e K = 7 (+ 15-19) conferidos no modelo
      novo, que reproduz o notebook: 106.816,21 e 106.788,34, mais baratas que o MILP salvo
      (106.826,95 e 106.822,62). K = 8 igual ao MILP (106.784,01, mesmas 8 linhas)
- [x] LP0 (Fuller sem N-1) nunca propõe linha: no SC-DCOPF os preços do caso base são todos iguais
      (nenhum limite do caso base ativo; o congestionamento vem das contingências)
- [ ] Rodar os 5 critérios no benchmark (λ = 1, lista reduzida) → tabela MILP × heurística
- [ ] Conferir as topologias de K = 6 e 7 no pandapower (passo V)
- [ ] Revisar a adaptação de PD/PW ao N-1 (normalização por |f₀|, sinal da eq. 42)
- [ ] Usar as topologias da heurística como warm start do MILP (`run_ots.py --warm-start-dir`)
- [ ] Modo de violação (LP com folgas) para o CS2

### Análise A+ - qualidade das soluções (`ots-sc-dcopf/solution-quality/ots-solution-quality.ipynb`)

- [x] Notebook criado: verificação por LP com topologia fixa (reproduz K0-K10), busca local
      (adicionar/trocar linha) e duais das contingências limitantes
- [ ] Rodar o notebook completo (salva as soluções melhoradas em `contingencies_improved/`)
- [ ] Rodar de novo o OTS nos K melhorados, partindo do warm start melhorado
      (o notebook principal já lê `_improved/`):
      ```
      cd project/ots-sc-dcopf
      ..\..\venv\Scripts\python.exe -u sweep_k.py --formulation redispatch_with_exclusions --k-min 3 --k-max 3 --time-limit 9000 *> logs/sweep_K3_rerun.log
      ```
- [ ] Atualizar a §1.1 do `RESULTS_NOTES.md` e o gráfico com os custos finais
      (fazer o `plot_k_sweep.py` também ler `_improved/`)
- [ ] (Opcional) Força bruta para K = 1 (177 LPs) como prova de otimalidade independente
- [ ] (Opcional) "Custo total" de cada contingência principal: tirar o estado e resolver de novo
      (um LP por contingência), já que o dual só dá o valor marginal

### Validação V - OTS com pandapower

- [ ] Validação a posteriori (remover as linhas abertas e simular cada estado)
- [ ] Verificar a conectividade por estado e reportar ilhas, se houver (pouco provável com o
      modelo novo, mas possível em princípio num estado de contingência de linha)
- [ ] Comparar com Hedman et al. (OTS com N-1 no IEEE 118): mesma ordem de grandeza da economia
      relativa (%) x número de linhas abertas. Formulações e dados diferem, então os valores
      absolutos não devem bater; conferir antes os dados do artigo

### Análise B - C_T completo (`redispatch_only`), deixada para depois

Código: `ots-sc-dcopf/full-ct-feasibility/core_screening.py` (vai virar notebook).

- [ ] Transformar o `core_screening.py` em notebook, na pasta `full-ct-feasibility/`
- Até agora: K ≤ 3 provado inviável; K = 4, 5, 6 sem decisão em 10 min (objetivo de custo)
- [x] Modo de chaveamento mínimo no `core_screening.py`: min sum(1 - z) sobre L^S, mesmas
      restrições, sem limite de K → K_min e uma topologia viável
      (`--min-switching --min-open 4`, opcional `--norel-time`)
- Primeiras rodadas (local, chaveamento mínimo em núcleos pequenos = caso base + as contingências
  listadas): 8-5 sozinha precisa de 3 abertas (provado); 38-65, gerador da barra 10 e os dois
  juntos precisam de 0; 8-5 + gerador da barra 10 precisa de 4 (provado); **8-5 + 38-65 não
  achou solução em 150 s**, nem as 3 juntas (nem o núcleo de 4 cenários em 8 min com NoRel)
- [x] O par 8-5 + 38-65 é **viável** (2026-11-09): a busca local gulosa no conjunto aberto
      (mínima violação de limite de fluxo, limites F flexíveis), partindo da topologia da 8-5,
      chegou a 0 com 7 abertas: 23-24, 23-32, 25-27, 26-25, 49-50, 65-66, 65-68 (LP exato:
      OPTIMAL, custo base 106.779,94 $/h nesse núcleo). Não está provado que é mínimo (limite
      inferior 3, vindo da 8-5). Por que foi difícil: com tudo fechado, a saída da 8-5
      sobrecarrega a 15-17 (fluxo 17 → 15) em 0,33 pu, e em 0,40 pu com a 38-65 também; o
      chaveamento precisa redirecionar o suprimento do bolsão das barras 1-16
- [ ] **Bloqueio atual: 8-5 + 38-65 + gerador da barra 10** (núcleo de 4 cenários). Essa
      topologia falha nas contingências do gerador da barra 10 e da 56-57.
      - A busca local travou em 0,021 pu de violação (18 abertas).
      - O MILP de mínima violação (8 min, 8 threads) achou 0,038 pu com bound 0. A relaxação do
        big-M é um modelo de transporte (sem KVL), então o bound não se move e o Gurobi não
        consegue provar inviabilidade assim.
      - N-1 sem o gerador da barra 10, partindo da topologia do par: ainda falham 12
        contingências (22-23, 26-30, 56-57 e 7 geradores). A busca local é lenta demais em
        núcleos desse tamanho.
      - A viabilidade do N-1 completo continua sem decisão.
- [x] Adicionado `--max-open N` ao `--min-switching` (corte sum(1 - z) ≤ N): busca só topologias
      com no máximo N ramos abertos, o que torna a pergunta finita
- [ ] Núcleo de 4 cenários com 4 ≤ abertas ≤ 10 (local, 8 threads, 8 min): sem solução, 7.140
      nós explorados, 4.134 ainda abertos, bound 4 → sem decisão. Rodar longo no cluster:
      ```
      cd project/ots-sc-dcopf/full-ct-feasibility
      python -u core_screening.py --min-switching --min-open 4 --max-open 10 --time-limit 7200 --norel-time 600 --threads 16 --max-iter 20 *> ../logs/minsw_max10_log.txt
      ```
      INFEASIBLE → nenhuma topologia com ≤ 10 linhas abertas cobre o N-1 completo (é uma prova,
      porque o núcleo é uma relaxação); viável → K_min ≤ n_open e uma topologia para a sweep
- [x] Notebook da Análise B criado: `full-ct-feasibility/ots-full-ct-feasibility.ipynb`
      (checagens: reproduz K = 0 da A; N-1 completo inviável na topologia original)
- [x] Rodada local 2026-11-13, modo `min_switching`, núcleo de 4 estados, 4 ≤ abertas ≤ 10,
      1 h, 16 threads, NoRel 600 s: **undecided**. 174.806 nós, nenhuma topologia encontrada,
      limite inferior parado em 4. Mesma causa da Análise A: a relaxação do big-M é fraca, e mais
      tempo provavelmente não resolve
- [ ] **Decidir o método de busca** (ler os artigos antes):
  - A. Benders combinatório: mestre só com z + subproblema LP com z fixo, cortes pelo IIS.
    Exato (prova inviabilidade); risco: muitas iterações. Codato & Fischetti (2006)
  - B. Metaheurística (GA, SA, tabu) com avaliação por LP: acha soluções, nunca prova
  - C. Formulação baseada em ciclos: exata e forte, mas trabalhosa. Kocuk et al. (2016)
  - D. Heurísticas por sensibilidade/duais (ranking de linhas candidatas): Fuller et al. (2012),
    Ruiz et al. (2012). Pode ser combinada com A (Benders só nas candidatas)
  - Escolher as candidatas por critério reproduzível (linhas sobrecarregadas nos estados críticos
    + vizinhas a 1–2 barras + linhas de soluções boas conhecidas), não só pelo congestionamento
  - Alternativa de escopo: B só com as contingências de linha (8-5, 38-65) e/ou medir quanto o
    OTS reduz a violação (já se chegou a 0,021 pu ≈ 2 MW com 18 abertas). Combinar com a orientação
  - **Decisão 2026-11-14: D (ranking), exigindo viabilidade.** O núcleo nunca passou de 4 cenários,
    então o gargalo é o número de linhas candidatas, não o de contingências. Plano:
    1. LP com folgas (feasRelax) no núcleo de 4 cenários, topologia completa → preços da violação
    2. Índice por linha: fluxo × diferença de preço entre as pontas (lógica do Fuller, com os
       preços da violação, não os de custo) → top 20–30 candidatas
    3. `--min-switching` com `set_LS` = só as candidatas (arquivo novo, sem mexer no original)
    4. Se achar topologia: checar o N-1 completo pelo LP (o próprio core screening faz isso)
    - Com L^S reduzido, "inviável" não é prova para o sistema completo (a prova de K ≤ 3 já existe)
    - Minimizar a violação fica só como plano reserva, se a viabilidade não sair
    - O mesmo código, com os preços de custo do K = 0, serve para acelerar a Análise A
- [ ] Achar K_min (ou provar que o N-1 completo é inviável para qualquer topologia)
- [ ] Rodar o OTS (objetivo de custo) em K_min, K_min + 1, ... com warm start a partir dela
- [ ] Comparar com a Análise A no mesmo K (custo de cobrir as 3 contingências extras)

### Revisão

- [ ] **Revisar todo o código escrito em conjunto**: `sc-dcopf.ipynb` (incl. Seção 10),
      `scdcopf-pandapower.ipynb`, `ots-sc-dcopf.ipynb`, `sweep_k.py`, `plot_k_sweep.py`,
      `solution-quality/ots-solution-quality.ipynb`, `full-ct-feasibility/core_screening.py`
      e o que a validação V e a Análise B acrescentarem

Notas:
- Não rodar dois jobs do Gurobi ao mesmo tempo com o número padrão de threads (cada um usa
  todos os núcleos). Para rodadas em paralelo, passar `--threads` ao `sweep_k.py` para que os
  jobs dividam os núcleos. A licença WLS aceitou 10 sessões simultâneas (testado em 2026-11-09).
- Rodar jobs longos no seu próprio PowerShell, não dentro do Claude (eles param se o app fechar),
  com o modo de suspensão do Windows em "Nunca" enquanto estiver na tomada.

## Cenários com renováveis (depois do caso base) - pergunta R

- [ ] Desenhar dois cenários no sistema de 118 barras:
  - concentrado: geração renovável longe da carga
  - distribuído: geração renovável e carga espalhadas pela rede
- [ ] Decisões de modelagem
  - [ ] Métrica de curtailment (ex.: sum_r (P_r^avail - P_r,0), em MW ou % do disponível)
  - [ ] Custo da renovável (custo zero deixa o LP degenerado: usar custo pequeno ou penalidade
        de curtailment)
  - [ ] Se as renováveis entram na resposta alpha (provavelmente não)
- [ ] Rodar SC-DCOPF e OTS-SC-DCOPF em cada cenário, com alguns K escolhidos a partir da curva
      da Análise A (ex.: K = 0, o joelho e a saturação)
- [ ] Sweep de penetração renovável com carga fixa (renováveis com curtailment,
      0 ≤ P_r ≤ P_r^avail): custo e curtailment x penetração, com e sem OTS
- [ ] Comparar as contingências limitantes (duais) entre os dois cenários: onde fica o gargalo
- Métricas principais: custo e curtailment

## Análise dos resultados e tese

- [ ] Consolidar os resultados de todos os casos (tabelas e figuras)
- [ ] Escrever a tese (resultados, discussão, conclusões)
