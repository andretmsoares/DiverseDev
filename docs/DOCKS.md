# Modelos de docas (v2)

Comparam docas **especializadas** por tamanho (`base_15`) com docas **nao especializadas** fixas. Todas com 15 docas.

| id | descricao | borrow | filas |
|---|---|---|---|
| `base_15` | 4 express (P), 6 padrao (M), 5 pesada (G) | `one_way` | uma por classe |
| `generic_15` | 15 docas identicas P/M/G | `none` | unica |
| `generic_nested_15` | `small` (P) x4, `medium` (P,M) x5, `large` (P,M,G) x6: capacidade fisica variada | `best_eligible` | uma por **tamanho de pedido** (P, M, G) |
| `generic_speed_15` | `slow` 0,75 x5, `normal` 1,0 x5, `fast` 1,25 x5 (soma das velocidades = 15), todas aceitam P/M/G | `none` | unica (`generica`) |

`base_15_no_borrow` e `mini_8` seguem iguais. Teste de regressao (`tests/test_dock_models.py`, `tests/golden_docks.json`): `base_15`, `base_15_no_borrow`, `mini_8` e `generic_15` dao exatamente as mesmas metricas de antes (4 estrategias, com falha de doca).

## Campos novos em `configs/docks.json`

- `speed` (grupo, padrao 1.0): tempo de servico = `PACK_MIN[tamanho] / speed`.
- `queue` (grupo): nome da fila; grupos com o mesmo nome compartilham a fila (padrao: o nome do grupo).
- `alias` (grupo): outro nome pelo qual a falha de doca do manifest pode referenciar o grupo (`large` responde por `pesada`, entao `dock_outage` derruba 2 das 6 docas `large`).
- `borrow: "best_eligible"`: ver abaixo.

## best_eligible

Uma fila (estrategia) por tamanho de pedido. Quando uma doca fica livre, pega o pedido de **menor `strategy.key(·, now)`** entre os topos das filas dos tamanhos que aceita; desempate (praticamente impossivel, pois a chave inclui `seq`): tamanho maior primeiro. Varios grupos livres: os grupos sao atendidos na ordem do arquivo, da **menos capaz para a mais capaz** (small, medium, large), para nao gastar doca grande a toa. Um pedido sem nenhuma doca que o aceite gera `ValueError`.

## Varias docas livres em fila unica (`generic_speed_15`)

Despacha-se primeiro a doca **mais rapida** (fast, normal, slow).

## Mapeamento das colunas

- `util_<grupo>`: sempre por **grupo de docas** (`small/medium/large`, `slow/normal/fast`, `express/...`). Minutos ocupados na janela [warmup, ultimo fim] / (docas x janela); nao pondera pela velocidade.
- `max_queue_<fila>` / `mean_queue_<fila>` e `queue_<fila>` na serie temporal: por **fila**. Em `one_way`/`none` a fila e a classe (`express`, `padrao`, `pesada`; `generica` em `generic_15` e `generic_speed_15`). Em `best_eligible` a fila e o **tamanho do pedido**: `queue_P`, `queue_M`, `queue_G`.
- `busy_<grupo>` (serie temporal): docas ocupadas por grupo.
- `n_loans`: `one_way`, pedidos servidos por doca de classe maior que a sua; `best_eligible`, pedidos servidos por uma doca cujo grupo aceita um tamanho **maior** que o do pedido (P em `medium`/`large`, M em `large`); `none`, 0.
- `idle_pct` = 100 - ocupacao media global das docas (em tempo, nao ponderada pela velocidade).
- Falha de doca de uma classe que a configuracao nao tem: vale para a unica classe se houver uma so; senao e ignorada (assim, `dock_outage` e **ignorada** em `generic_speed_15`; em `generic_nested_15` vale para `large` por `alias`). Isso tira a falha do cenario nesses modelos; compare `dock_outage` com cautela.
- `runs.csv`/`queue_timeseries.csv`: colunas existentes mantidas; as colunas por grupo/fila sao a uniao entre as configuracoes executadas (vazio quando nao se aplica).
