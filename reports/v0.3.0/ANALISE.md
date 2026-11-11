# Análise dos resultados v2 (janelas apertadas e cinco configurações de docas)

Experimento: dados com perfil de janelas **tight** (30 a 120 min), 30 sementes de avaliação (0 a 29) e 10 de calibração (1000 a 1009), 12 estratégias, 21.540 execuções (mais 480 de calibração). Docas comparadas (15 docas, capacidade nominal equivalente):

| id | descrição |
|---|---|
| `base_15` | especializada por tamanho: 4 Express (P), 6 Padrão (M), 5 Pesada (G), empréstimo de mão única |
| `base_15_no_borrow` | a mesma, sem empréstimo |
| `generic_15` | 15 docas idênticas, fila única, qualquer pedido (tamanho fixo) |
| `generic_nested_15` | tamanhos variados por capacidade: 4 small (P), 5 medium (P, M), 6 large (P, M, G); a doca livre pega a menor chave entre os tamanhos que aceita |
| `generic_speed_15` | tamanhos variados por velocidade: 5 a 0,75×, 5 a 1,0×, 5 a 1,25×; qualquer pedido, fila única |

Tabelas completas em `report.md`; gráficos em `plots/` (o mapa `13_mapa_estrategia_doca.png` resume estratégia × doca).

## 1. Veredito do critério: EDF, em todas as configurações de docas

O prazo virtual (α de 0,5 a 5) não atende ao critério em `base_15` nem em nenhuma das outras quatro configurações. Na calibração (sementes separadas) nenhum α passa nos três cenários decisivos.

Com as janelas apertadas, os cenários agora discriminam. Em `peak_105` (docas `base_15`) o VIP atrasado no EDF é 11,0%.

| α | VIP atrasado em `peak_105` | % atrasados vs EDF | P99 vs EDF | passa? |
|---|---|---|---|---|
| 1 | 3,1% (-72%) | +3,6 pp | +77% | não |
| 2 | 0,9% (-92%) | +6,2 pp | +197% | não |
| 3 | 0,4% (-96%) | +6,8 pp | +313% | não (só passa em `black_friday`) |

O bônus de score protege VIPs quase por completo no pico, mas empurra os pedidos de score baixo para o atraso: mais atrasados no total e uma cauda muito pior. Em sobrecarga (125%) o ganho de VIP é parcial (α = 3: de 71% para 40%). Como o VIP foi rebaixado a critério secundário, o EDF permanece.

## 2. Docas especializadas × não especializadas (foco desta rodada), EDF

| cenário | métrica | base_15 | sem empréstimo | generic_15 | nested | speed |
|---|---|---|---|---|---|---|
| `peak_105` | % atrasados | 14,1 | 17,7 | **1,6** | 2,7 | 1,7 |
| `peak_105` | P99 (min) | 18 | 23 | 1 | 2 | 1 |
| `black_friday` | % atrasados | **34,8** | 37,2 | 59,9 | 36,1 | 59,9 |
| `black_friday` | P99 (min) | 258 | 257 | **100** | 154 | 100 |
| `promo_g_burst` | % atrasados | 11,7 | 11,7 | **0,0** | 12,6 | 0,0 |
| `mix_shift_33` | % atrasados | 29,7 | 29,7 | 30,5 | **27,9** | 30,5 |
| `mix_shift_33` | P99 (min) | 656 | 656 | **21** | 393 | 21 |
| `overload_125` | % atrasados | 74,4 | 74,8 | 73,9 | 73,6 | 73,9 |

**Achados**

1. **Juntar a capacidade (docas não especializadas) absorve melhor picos e rajadas.** Em `peak_105` o EDF cai de 14,1% para 1,6% de atrasados; em `promo_g_burst`, de 11,7% para 0%; a cauda em `mix_shift_33` cai de 656 para 21 min. Na especializada, as docas Express (P) chegam a ~95% de utilização e viram gargalo (23,6% dos P atrasados em `peak_105`), enquanto outras classes ficam ociosas. Em `mix_shift_33` a ociosidade média chega a 41%, os pedidos G sofrem (91% atrasados) e P e M ficam com 0%.
2. **O empréstimo ajuda, mas pouco:** 14,1% contra 17,7% de atrasados no pico e +13 pedidos/h; é bem menos que o ganho de juntar tudo.
3. **`black_friday` é a exceção:** a especializada atrasa menos pedidos (34,8% contra 59,9% da genérica), porque **isola** o excesso de G numa fila própria e mantém P e M andando (14% e 43% atrasados), em vez de espalhar o atraso por todos (~60% em todos os tamanhos). O preço é a cauda: P99 de 258 contra 100 min, concentrada nos pedidos G (72% atrasados).
4. **`generic_nested_15` é o melhor equilíbrio realista:** respeita a restrição física (G só em doca grande) e, ao deixar as docas maiores atenderem pedidos menores, tem 2,7% de atrasados no pico (contra 14,1% da especializada), 36,1% em `black_friday` (próximo dos 34,8%) e a cauda de `mix_shift_33` cai de 656 para 393 min. Fica pior que a genérica uniforme, que é uma hipótese otimista: ela supõe que qualquer doca embala qualquer pedido no mesmo tempo.
5. **`generic_speed_15` ≈ `generic_15`:** com a mesma capacidade total (soma das velocidades = 15) e fila única, a velocidade variada quase não muda os resultados (por exemplo, 1,7% contra 1,6% no pico). Conferi que a velocidade é de fato aplicada: as utilizações por grupo diferem.
6. **Em sobrecarga (125%) a configuração de docas quase não importa** (~74% atrasados em todas); falta capacidade.

**Recomendação para a decisão de docas:** preferir uma configuração **agrupada por capacidade** (`generic_nested_15`) à separação rígida por tamanho. A especializada pura só compensa quando se quer isolar rajadas de pedidos grandes.

## 3. Outros achados (janelas apertadas, `base_15`)

- **FIFO × EDF:** em `peak_105`, atrasados 20,1% → 14,1% e P99 34,4 → 18,3 min. Em sobrecarga o EDF não melhora o % de atrasados (74,4% contra 73,0% do FIFO, efeito dominó ao priorizar pedidos já vencidos), mas tem o menor P99 (165 min).
- **`two_queues` e WSPT** reduzem o % de atrasados em sobrecarga (23%), mas com P99 de ~800 min: abandonam pedidos.
- **Algoritmo de ordenação:** o heap continua sendo o mais barato, com resultados idênticos (0 divergências em 120 execuções). Em `overload_125`, EDF: heap 22 operações por pedido e 0,64 s de CPU; Insertion 105 e 0,8 s; Selection 330 e 2,2 s; Merge 1.503 e 10 s; Quick (pivô fixo) 41.784 e 113 s.

## 4. Ressalvas

- **Alta variância entre sementes em `peak_105`** (por exemplo, a semente 0 teve 12% de atrasados na genérica e as sementes 1 e 2 tiveram 0%); use os intervalos de confiança do `report.md`.
- **`dock_outage`:** em `generic_speed_15` a falha de doca é ignorada (não há grupo Pesada); a comparação desse cenário só vale para as outras configurações.
- **A genérica uniforme e a de velocidade são otimistas:** ignoram a restrição física de tamanho do pedido.
- **A explicação do `black_friday` (isolamento da fila G) é uma hipótese** apoiada nos atrasos por tamanho; não foi testada isoladamente.
- O `generic_nested_15` usa a regra "menor chave entre os tamanhos aceitos", que pode atrasar pedidos G quando há muitos P e M com prazo curto (85,7% dos G atrasados em `mix_shift_33`); outras regras de despacho não foram testadas.
- Bônus de score, faixas, aging e limite de 60 min dos concorrentes não foram calibrados com o mesmo rigor; dados sintéticos favorecem quem usa o score.
- Os limites do critério (50% de redução de VIP, 1 pp, 20% de P99) são sugestões do grupo.

## 5. Próximos passos
1. Testar outra regra de despacho para o `generic_nested_15` (por exemplo, reservar docas grandes para G).
2. Variar o número de docas por grupo (dimensionamento), em vez de uma única divisão.
3. Teste A/B em região piloto (EDF contra o prazo virtual, e docas agrupadas contra especializadas).
