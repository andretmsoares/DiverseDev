# Estratégias, backends e simulador (notas de implementação)

Complementa `docs/CONTRACT.md` (fonte de verdade). Aqui: definição exata das chaves, decisões, complexidade e como estender.

## Chaves (menor = mais prioritário)

| impl | chave | observação |
|---|---|---|
| `fifo` | `(seq)` | |
| `edf` | `(deadline, -score, seq)` | |
| `composite` | `(-score / max(deadline-now, 1), seq)` | pedido atrasado tem divisor 1 (sem divisão por zero) e, por isso, razão = score: tende a ficar à frente dos demais |
| `two_queues` | urgente `(0, -score, seq)` se `deadline-now <= urgent_limit_min`, senão `(1, seq, 0)` | urgentes sempre antes; migração normal -> urgente exata |
| `bands_aging` | `(faixa, -(score + aging*(now-arrival)), pack_min, seq)`, `faixa = floor(max(deadline-now,0)/band_min)` | atrasados ficam na faixa 0 |
| `wspt` | `(-(score/pack_min), seq)` | |
| `virtual_deadline` | `(deadline - alpha*score, pack_min, seq)` | `alpha=0` dá a mesma ordem de prazo do EDF |

Exemplo do guia (A: 30/90/P, B: 70/55/G, C: 20/20/P, agora=0): FIFO=A, EDF=C, composite=B, two_queues=B, bands_aging=C, WSPT=A, VD(alpha=1)=B (testado).

## Decisões de implementação

- **Estáticas** (`fifo`, `edf`, `wspt`, `virtual_deadline`): `IndexedHeap` (heap binário com mapa `order_id -> posição`, sift manual). push/pop/update/cancel O(log n); `peek(k)` por heap auxiliar de índices, O(k log k), sem copiar o heap.
- **two_queues**: dois `IndexedHeap` (urgentes por score, normais por seq) + heap de instantes de migração `deadline - limite`, com invalidação por versão. Cada pedido migra exatamente quando o relógio alcança o instante. O(log n) por operação.
- **bands_aging**: `aging*now` é comum a todos os pedidos, então a ordem *dentro* da faixa é estática (`score - aging*arrival`). Um `IndexedHeap` por faixa e um heap de instantes de troca de faixa (`deadline - b*band_min`). Exato, O(log n).
- **composite**: único caso sem estrutura exata barata (a ordem relativa muda continuamente). Usa `heapq` com **reavaliação periódica**: as chaves são recalculadas e o heap refeito (O(n)) quando o relógio avançou `refresh_min` (padrão 1 min) desde a última reconstrução; pedidos novos entram com a chave do instante. Trade-off: no pior caso, a escolha usa chaves até 1 min defasadas; `refresh_min=0` é exato (reconstrói a cada instante novo, mais lento). cancel/update por remoção preguiçosa. `ops` do composite é **estimado** (heapify ~2n, push/pop ~log2 n), pois o `heapq` é em C. Os testes comparam `two_queues`, `bands_aging` e `composite(refresh_min=0)` com uma referência de força bruta.
- **ops**: cada comparação e cada movimento de elemento soma 1 num contador compartilhado com os heaps/filas internos (`Strategy.ops`).
- **update**: altera `priority_score` e/ou `deadline_min` do objeto `Order` da fila (o simulador trabalha em cópias, os dados de entrada não são alterados) e reposiciona.

## Backends de ordenação (CONTRACT §5b)

`make_strategy(impl, backend="heap"|"insertion"|"selection"|"merge"|"quick", **params)`, só para as estáticas. Implementados à mão (sem `sorted()`/`list.sort`; o `sorted` só aparece no *setup* do benchmark). Mesma chave => mesma ordem de despacho (testado contra o heap em sequências aleatórias e em simulações completas).

| backend | push | pop | update / cancel | observação |
|---|---|---|---|---|
| `heap` | O(log n) | O(log n) | O(log n) | padrão |
| `insertion` | O(n) (inserção linear em lista ordenada) | O(1) | O(n) (busca) | |
| `selection` | O(1) | O(n) (varre o mínimo) | O(n) | `peek(k)`: k varreduras |
| `merge` | O(1) | O(n log n) se mudou desde o último pop | O(n) | Merge Sort bottom-up iterativo, estável; remoção não "suja" a lista |
| `quick` | O(1) | O(n log n) médio, **O(n²)** em fila ordenada | O(n) | pivô fixo (primeiro elemento) e pilha explícita (sem recursão) |

`merge`/`quick` reordenam a lista **inteira** quando houve push/update desde o último pop (conforme o adendo). Em filas grandes e quase ordenadas o `quick` com pivô fixo é muito lento (14 s por pop com n = 10 mil); por isso a comparação completa de backends deve usar poucos cenários/seeds.

## Simulador: decisões e leituras do contrato

- **Eventos simultâneos**: ordem no mesmo instante: fim de embalagem, fim de falha, início de falha, chegada, evento update/cancel. O despacho só roda depois de aplicados *todos* os eventos do instante, para que pedidos que chegam juntos concorram pela doca pela chave (e não por ordem do arquivo).
- **Despacho**: classes em ordem crescente; cada doca livre pega o topo da própria fila; senão (`one_way`) o de menor `strategy.key(·, now)` entre os topos das classes menores (`loan`).
- **Falhas**: `count` docas da classe ficam indisponíveis de `start_min` a `end_min`; doca ocupada termina o pedido em curso e então não pega outro. Se a configuração de docas não tem a classe do manifest: com **uma classe só** (ex.: `generic_15`) a falha vale para ela; com várias classes é ignorada.
- **Atraso** usa o `deadline_min` vigente na conclusão (após `update`); `is_vip`/VIP usa o score vigente na conclusão.
- **Warm-up**: valor do manifest (`warmup_min`, padrão 60). Cancelamentos contam em `n_cancelled` só para chegadas fora do warm-up. Eventos para pedidos em embalagem/concluídos/inexistentes são ignorados.
- **Métricas**: percentuais em 0-100; médias de atraso sobre todos os pedidos medidos (`mean_delay_late_min` só sobre atrasados); percentis por interpolação linear sobre todos os medidos (inclui atraso 0); `mean_wait_min` = início da embalagem − chegada; `util_<classe>` = minutos ocupados em [warmup, último fim] / (docas × janela) (denominador nominal, não desconta falhas); `idle_pct` = 100 − utilização global; `max_queue`/`mean_queue` = fila da classe (sem contar pedidos em embalagem) na janela [warmup, último fim]; `ops_per_order` = `ops_total / chegadas` (inclui warm-up); `n_loans` conta todos os empréstimos; `cpu_ms` = tempo de parede da simulação.
- **Saídas**: `queue_timeseries.csv` e `delays_seed0.csv` só para seed 0 e backend `heap` (os demais backends produzem a mesma ordem). A amostra de `t` mostra o estado depois de todos os eventos em instantes ≤ t. Com `--calibration` (seeds 1000-1009) os arquivos levam o prefixo `calibration_` para nunca se misturarem com os de avaliação. Para backends diferentes de `heap`, `--strategies all` usa a lista `backend_strategies` de `configs/strategies.json`; com ids explícitos, usa os que forem estáticos.
- **Desempenho típico** (Python 3.7, um dia de ~9 mil pedidos, 125% de carga): 0,3-0,8 s por run (heap); composite e bands_aging são os mais caros.

## Como adicionar uma estratégia

1. Estática: subclasse de `StaticHeapStrategy` em `mps/strategies/static.py`, definindo `_keyfn(order)` (tupla, menor primeiro, terminando em `seq` para ordem total) — ganha todos os backends. Dependente do tempo: subclasse de `OpsMixin, Strategy` implementando a interface de `base.py` (use `IndexedHeap(self._cnt)` e um heap de instantes de mudança de chave quando possível).
2. Registre em `REGISTRY` (`mps/strategies/__init__.py`) e, se for estática, em `STATIC_IMPLS`.
3. Acrescente a entrada em `configs/strategies.json` (commit separado, aviso aos demais módulos).
4. Adicione ao teste de força bruta (`tests/test_strategies.py`, lista `ALL`) e ao exemplo do guia.

## Reproduzir

```
python -m unittest discover -s tests -v
python -m mps.sim --data data/synthetic --out results --scenarios all --strategies all --docks base_15 --seeds 0-29 --workers 4
python -m mps.sim --data data/synthetic --out results/backends --scenarios normal_85,peak_105,overload_125 --strategies edf,vd_a1 --backends heap,insertion,selection,merge --seeds 0-4 --workers 4
python scripts/bench_sorting.py            # results/bench_sorting.csv (n = 1k, 10k, 50k)
```
