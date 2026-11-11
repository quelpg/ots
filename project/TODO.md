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

Os resultados e a interpretação de cada análise ficam em `ots-sc-dcopf/RESULTS_NOTES.md` (§0 tem o
mapa das análises e onde está cada código).

---

## IEEE 118 barras - caso base

- [x] **1** - SC-DCOPF com a formulação revisada (custo só do caso base, F^em = 1,15 F^max,
      acoplamento preventivo, fatores de participação alpha, theta em ±0,6 rad)
- [x] Análise de vulnerabilidade (Seção 10 de `sc-dcopf/sc-dcopf.ipynb`).
      Exclusões: linha 8-5 (sozinha), linha 38-65 e gerador da barra 10 (em conjunto)
- [x] Validação do SC-DCOPF com pandapower, a posteriori (194/194 estados passam)
- [x] OTS-SC-DCOPF com a formulação revisada (K = 0 reproduz o SC-DCOPF)
- [ ] Confirmar a exclusão: no código é a linha **38-65**; no resumo do TCC aparece 38-37

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
