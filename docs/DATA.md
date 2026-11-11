# Dados sinteticos (mps.datagen)

## Como gerar

```
python -m mps.datagen --scenarios all --seeds 0-29 --out data/synthetic      # avaliacao
python -m mps.datagen --scenarios all --calibration --out data/synthetic     # seeds 1000-1009
python -m mps.datagen --scenarios normal_85,peak_105 --seeds 0,5,9 --out data/synthetic
```

Saida: `data/synthetic/<cenario>/seed_<N>/{orders.csv,events.csv}` e `data/synthetic/<cenario>/manifest.json`
(formatos em `docs/CONTRACT.md` secao 3). Colunas extras de `orders.csv`: `region, distance_km, sla_min, value_brl, seller_reputation`.
Tempo de geracao: ~0.3 s por seed/cenario. `--calibration` e `--seeds` sao exclusivos; misturar 0-29 com 1000-1009 e rejeitado.
Rodar duas vezes com a mesma seed e o mesmo cenario produz arquivos identicos byte a byte
(`random.Random` com seed derivada de `crc32(scenario_id)` e da seed; sem `hash()`). O manifest acumula as seeds ja geradas
(uniao ordenada) e traz `seed_stats` por seed (n_orders, taxa/h, % VIP, mix real, contagem por regiao, updates, cancels) para auditoria.
Parametros em `configs/scenarios.json` (defaults, perfis, regioes, cenarios).

## Cenarios (capacidade nominal 480/h, `dock_config` = `base_15`)

`base_rate_per_h` e a **media do dia** (o perfil e normalizado para media 1; vales e picos ficam acima/abaixo).

| cenario | media/h | descricao |
|---|---|---|
| `normal_85` | 408 | perfil diario completo (vales ~0.6x, picos ~1.3x) |
| `peak_105` | 504 | idem, 105% |
| `overload_125` | 600 | idem, 125% |
| `black_friday` | 518 (108%) | perfil suave x rampa; plateau de 4 h (t=360-600) em ~140% (~672/h); G ~22% do mix entre t=300 e 660 (~18% no dia); 6% de pedidos com update, 80% deles mexendo no prazo |
| `promo_g_burst` | 480 | perfil suave; entre t=360 e 480 o mix vira 33/27/40 (G ~40%) |
| `mix_shift_33` | 408 | mix 34/33/33 |
| `dock_outage` | 408 | igual a `normal_85`; manifest traz outage `pesada` x2, t=360-540 |
| `regional_mix` | 456 (95%) | BR 45%, MX 25%, AR/CO/CL 10% cada |
| `sweep_70`..`sweep_130` | 70%..130% | passo 5, perfil diario suave (amplitude 0.35) |

## Premissas de realismo

- **Chegadas:** Poisson nao homogeneo por *thinning*. Taxa = base x perfil horario (06h-22h, interpolado entre centros de hora, vale no almoco e ~13h-14h, picos de manha e da noite) x rampas (`rate_knots`), por regiao.
- **Janela:** `SLA` por faixa (por regiao) e janela log-normal com mediana 0.8 x SLA, truncada em [30, 240] min por rejeicao. SLA apertado => janela curta.
- **Regioes (`regional_mix`):** cada pais tem distribuicao de SLA, ruido da janela (sigma 0.20 CL a 0.40 AR), distancia mediana, reputacao de vendedor, fator de valor e deslocamento do perfil diario (MX +90 min, CO +30, AR -60). AR: SLA mais apertado e mais ruidoso; MX: SLA mais folgado; CL: SLA apertado e pouco ruido. Nos demais cenarios todos os pedidos sao `BR`.
- **Tamanho e valor:** tamanho sorteado pelo mix vigente no instante de chegada; valor log-normal com mediana P 60, M 180, G 700 BRL (sigma 0.8) x fator da regiao.
- **Fator latente "cliente premium":** uma normal por pedido correlaciona (rho 0.5) SLA apertado, distancia e valor, o que alarga a distribuicao do score.
- **priority_score** = 0.40 SLA + 0.20 distancia + 0.25 valor + 0.15 reputacao, cada componente em 0-100: SLA = (240-janela)/210; distancia e valor por log entre 10 e 1500 (km / BRL); reputacao = beta(a,b) x 100. Distancias maiores = maior prioridade (premissa nossa: exigem despacho mais cedo). Resultado: VIP (>=70) ~19-22% na maioria dos cenarios e ~26% em `mix_shift_33` (mais G, itens caros).
- **Eventos:** 3% dos pedidos com `update` (score e/ou prazo; prazo novo > tempo do evento) e 2% com `cancel`, mutuamente exclusivos; `time_min` uniforme dentro de [chegada, prazo original].

## Limitacoes conhecidas

- Taxa observada varia ~2-3% em torno da meta por seed (Poisson); a media de varias seeds converge.
- Regiao nao altera o mix de tamanhos nem os tempos de embalagem; so SLA, valor, distancia, reputacao e perfil.
- Score nao e re-sorteado em `update`: novo score = antigo + ruido N(0,15), truncado em [0,100]; o VIP pode mudar.
- Sem sazonalidade entre dias, sem dependencia entre pedidos (nao ha lotes/clientes repetidos).
- O dia termina em 960 min; nao ha pedidos depois (o simulador esvazia as filas).
- Pedidos criticos (janela 30 min, tarde no dia) podem ter prazo posterior ao fim do dia; e esperado.
