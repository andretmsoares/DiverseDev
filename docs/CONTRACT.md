# Contrato entre módulos (VelozMart MPS)

Este documento é a fonte de verdade para quem implementa `mps.datagen`, `mps.strategies`/`mps.sim` e `analysis/`.
Mudanças aqui exigem um PR próprio (`docs(contract): ...`) e aviso aos demais módulos.

## 1. Ambiente

- Python **3.7+** (a máquina do grupo roda 3.7.9). Sem `:=`, sem `list[int]`/`dict[str, int]` (use `typing`), `dataclasses` é permitido.
- Núcleo (`mps/datagen`, `mps/strategies`, `mps/sim`): **apenas biblioteca padrão**. Gerador aleatório: `random.Random(seed)`.
- Análise (`analysis/`): `pandas`, `numpy`, `matplotlib` (ver `requirements.txt`).
- Testes: `python -m unittest discover -s tests -v` (sem pytest).
- Execução sempre a partir da raiz do repositório: `python -m mps.datagen ...`, `python -m mps.sim ...`.

## 2. Tempo e unidades

- Tempo em **minutos (float)** desde `t = 0` (início do dia operacional). Dia operacional = 960 min (16 h, 06:00 a 22:00).
- `deadline_min = arrival_min + dispatch_window_min` (prazo **absoluto**, constante).
- `priority_score` em [0, 100]. **VIP = score >= 70** (`mps.models.VIP_THRESHOLD`).
- Tamanhos: `P`, `M`, `G`. Tempo de embalagem: P=1, M=2, G=4 min (`mps.models.PACK_MIN`).

## 3. Entrada: dados sintéticos (`mps.datagen` produz, `mps.sim` consome)

Pasta: `data/synthetic/<scenario_id>/seed_<N>/` com `orders.csv`, `events.csv` e, por cenário, `data/synthetic/<scenario_id>/manifest.json`.

### orders.csv (colunas obrigatórias, nesta ordem; colunas extras vão ao final)

| coluna | tipo | descrição |
|---|---|---|
| `order_id` | str | `O000001`..., único na seed |
| `arrival_min` | float | chegada, ordenado crescente |
| `dispatch_window_min` | float | janela até o prazo no momento da chegada (> 0) |
| `deadline_min` | float | `arrival_min + dispatch_window_min` |
| `priority_score` | float | 0 a 100 |
| `size_category` | str | P, M ou G |

Extras sugeridos: `region` (BR, MX, AR, CO, CL...), `distance_km`, `sla_min`, `value_brl`, `seller_reputation`.

### events.csv (atualizações e cancelamentos; pode ter só o cabeçalho)

`event_id,time_min,order_id,kind,new_score,new_deadline_min`
- `kind` = `update` (campos novos preenchidos ou vazios = sem mudança) ou `cancel`.
- `time_min` está entre a chegada do pedido e o seu prazo; eventos para pedido já despachado são permitidos (o simulador ignora).

### manifest.json (por cenário)

`scenario_id`, `description`, `seeds`, `duration_min`, `base_rate_per_h`, `size_mix` (ex.: `{"P":0.5,"M":0.35,"G":0.15}`), `rate_profile` (descrição), `dock_config` (id em `configs/docks.json`), `outages` (lista, ver §4), `warmup_min` (padrão 60), `notes`.

### Seeds

- **Avaliação:** 0..29. **Calibração (α e parâmetros):** 1000..1009. Nunca misturar.

### Catálogo mínimo de cenários (`configs/scenarios.json`)

Capacidade nominal do `base_15` = **480 pedidos/h** (mix 50/35/15). Rótulos de carga são relativos a ela.

| scenario_id | descrição |
|---|---|
| `normal_85` | dia útil, 85% (408/h) com perfil diário (vales e picos) |
| `peak_105` | dia de pico, 105% (504/h) |
| `overload_125` | sobrecarga sustentada, 125% (600/h) |
| `black_friday` | rampa até ~140% por 4 h, G sobe para ~22% do mix, mais atualizações de prazo |
| `promo_g_burst` | 100% médio, com rajada de 2 h em que G chega a ~40% do mix |
| `mix_shift_33` | mix 33/33/33 a 408/h (estressa a classe G) |
| `dock_outage` | `normal_85` com 2 docas Pesada fora do ar por 3 h |
| `regional_mix` | hub multi-país (BR, MX, AR, CO, CL) com perfis de SLA, volume e ruído distintos |
| `sweep_70` ... `sweep_130` | passo de 5 (13 cenários), carga constante com perfil diário suave |

Realismo exigido: chegadas por processo de Poisson não homogêneo; janelas log-normais em 30 a 240 min (truncadas), mais curtas quando o SLA é apertado; ~3% de pedidos com atualização e ~2% com cancelamento; valor do item correlacionado ao tamanho; **`priority_score` calculado a partir de componentes** com os pesos SLA 40%, distância 20%, valor 25%, reputação 15% (pesos do documento do projeto); fração de VIPs entre 15% e 30%.

## 4. Docas (`configs/docks.json`)

Cada configuração tem `classes` (ordenadas da menor para a maior), cada uma com `name`, `sizes` aceitos e `count`, e `borrow` (`"one_way"` ou `"none"`).
Um **heap/fila por classe**. Pedido vai para a classe cujo `sizes` contém seu tamanho.

- Doca livre: despacha o topo da fila da sua classe.
- `one_way`: se a fila da própria classe está vazia, pega o pedido de **menor chave** (`strategy.key`) entre os topos das classes **menores**. Nunca o contrário. Conta como `loan`.
- `none`: não empresta.
- Tempo de serviço = `PACK_MIN[size]` (determinístico), sem jitter por padrão.
- `outages` (no manifest do cenário): `[{"class": "pesada", "count": 2, "start_min": 360, "end_min": 540}]`. A doca fora do ar termina o pedido em curso e só volta a pegar pedido no `end_min`.

## 5. Estratégias (`mps.strategies`)

Interface em `mps/strategies/base.py` (classe `Strategy`). O simulador cria **uma instância por fila de classe de doca**.

`registry` em `mps/strategies/__init__.py`: `make_strategy(impl, **params) -> Strategy`.
Implementações exigidas (`impl`):

| impl | chave (menor primeiro, salvo indicação) |
|---|---|
| `fifo` | `(seq,)` |
| `edf` | `(deadline_min, -score, seq)` |
| `composite` | maior `score / max(deadline_min - now, 1)`; desempate `seq`. Chave muda com `now` |
| `two_queues` | urgente se `deadline_min - now <= urgent_limit_min` (60): ordem por maior score; normais por `seq`; urgentes sempre antes; pedidos migram com o tempo |
| `bands_aging` | faixa = `floor(max(deadline_min - now, 0) / band_min)` (30); dentro da faixa maior `score + aging_pts_per_min*(now - arrival_min)` (0,2); depois menor `pack_min`, depois `seq` |
| `wspt` | maior `score / pack_min`; desempate `seq` |
| `virtual_deadline` | `(deadline_min - alpha*score, pack_min, seq)`; `alpha` em minutos por ponto |

Estratégias com chave estática (`fifo`, `edf`, `wspt`, `virtual_deadline`) devem usar **heap com mapa `order_id -> posição`** (O(log n) para push, pop, update, cancel). As de chave dependente do tempo podem usar varredura ou reconstrução periódica, mas precisam ser corretas e razoavelmente rápidas (alvo: um dia de ~8 mil pedidos em poucos segundos).

Contador `ops`: cada estratégia incrementa `self.ops` a cada comparação/troca de elementos (custo do algoritmo, independente de CPU).

`configs/strategies.json` lista as execuções (`id`, `impl`, `params`). A tag `virtual_deadline` varia `alpha` em 0, 0.5, 1, 2, 3, 5.

## 5b. Algoritmos de ordenação (backends da fila) — adendo

Os 5 algoritmos do guia (Insertion, Selection, Merge, Quick, Heap) são implementados como **backends** intercambiáveis da fila das estratégias de chave estática (`fifo`, `edf`, `wspt`, `virtual_deadline`). Mesma chave => mesma ordem de despacho (a chave inclui `seq`, então a ordem é total); muda só o custo.

| backend | como mantém a fila |
|---|---|
| `heap` (padrão) | heap + mapa id->posição |
| `insertion` | lista ordenada; push por inserção linear |
| `selection` | lista sem ordem; pop varre a lista procurando o mínimo |
| `merge` | reordena tudo com Merge Sort próprio sempre que a fila mudou antes de um pop |
| `quick` | idem com Quick Sort próprio, pivô fixo (primeiro elemento), para expor o pior caso em fila quase ordenada |

Todos contam `ops` (comparações/trocas) e respeitam a interface `Strategy` (inclusive `update`, `cancel`, `peek`). Parâmetro `backend` em `make_strategy(impl, backend="heap", **params)`.
`configs/strategies.json` ganha a seção `"backends": ["heap","insertion","selection","merge","quick"]` e `"backend_strategies": ["edf","vd_a1"]` (mínimo; mais é bem-vindo).
CLI do simulador: `--backends heap,insertion,...` (padrão `heap`). `runs.csv` ganha a coluna `backend` logo após `strategy_id`. Como os backends O(n) ou O(n log n) por operação são lentos sob fila grande, a comparação completa de backends roda nos cenários `normal_85`, `peak_105` e `overload_125` com menos seeds (ex.: 0-4); o script `scripts/bench_sorting.py` (n = 1k, 10k, 50k) também é obrigatório e gera `results/bench_sorting.csv` com `algorithm,n,op,ms_per_op,ops_per_op`.

## 6. Simulador (`mps.sim`)

Evento discreto: chegadas, eventos (`update`, `cancel`), fim de embalagem, início/fim de falha de doca. Ao liberar uma doca (ou chegar pedido com doca livre), despacha conforme §4. Atrasos:

- `completion_min` = fim da embalagem.
- `delay_min = max(0, completion_min - deadline_min)`; **atrasado** = `delay_min > 0`.
- Pedidos cancelados antes de iniciar a embalagem saem das métricas. Pedido já em embalagem não é cancelado.
- **Warm-up:** pedidos com `arrival_min < warmup_min` (60) executam mas **não entram** nas métricas.
- A simulação continua depois do último pedido até esvaziar as filas.
- `throughput_per_h` = pedidos concluídos (fora do warm-up) por hora, entre `warmup_min` e o último `completion_min`.

CLI: `python -m mps.sim --data data/synthetic --out results --scenarios all --strategies all --docks base_15 --seeds 0-29 --workers 4`
(`--seeds` aceita `0-29` ou lista `0,5,9`; `--docks` aceita vários ids; `--strategies` aceita ids de `strategies.json`.)

### Saídas (`results/`)

**`runs.csv`** — uma linha por (scenario, dock_config, strategy_id, seed):
`scenario_id,dock_config,strategy_id,impl,alpha,seed,n_orders,n_late,pct_late,mean_delay_min,mean_delay_late_min,p95_delay_min,p99_delay_min,max_delay_min,n_vip,vip_pct_late,throughput_per_h,mean_wait_min,delay_mean_P,delay_mean_M,delay_mean_G,pct_late_P,pct_late_M,pct_late_G,util_<classe>...,idle_pct,n_loans,max_queue_<classe>...,mean_queue_<classe>...,ops_total,ops_per_order,cpu_ms,n_cancelled`
(colunas por classe usam o `name` da config; para `generic_15` há uma só.)

**`queue_timeseries.csv`** — só seed 0 de cada (scenario, dock_config, strategy_id): `scenario_id,dock_config,strategy_id,seed,time_min,queue_<classe>...,busy_<classe>...` amostrado a cada 5 min.

**`delays_seed0.csv`** — só seed 0: `scenario_id,dock_config,strategy_id,order_id,size_category,is_vip,delay_min,wait_min` (para CDF).

**`runs.meta.json`** — versões, data/hora, comando, git commit.

Determinismo: mesmos dados + mesma configuração => mesmas métricas (exceto `cpu_ms`).

## 7. Fluxo de trabalho no git

Ver `CONTRIBUTING.md`. Cada módulo vive na sua branch (`feat/datagen`, `feat/strategies-sim`), com commits no padrão Conventional Commits, e entra em `main` por merge `--no-ff` após os testes passarem.
