# Análise dos resultados (v0.1.0)

Experimento: 21 cenários sintéticos × 30 sementes, 12 estratégias, docas `base_15` (4 Express, 6 Padrão, 5 Pesada, empréstimo de mão única); variações `generic_15` e `base_15_no_borrow` nos cenários de carga e estresse; 4 algoritmos de ordenação como backend (sementes 0 a 9). Total: 12.840 execuções. Detalhes e tabelas completas em `report.md`; gráficos em `plots/`.

## Veredito do critério (seção 5.3): EDF

Nenhum prazo virtual (α = 1, 2 ou 3) atende ao critério nos três cenários decisivos (`peak_105`, `overload_125`, `black_friday`).

| α | VIP atrasado em `overload_125` (EDF: 33,8%) | P99 vs EDF | efeito em `black_friday` |
|---|---|---|---|
| 1 | 24,0% (-29%) | +6,5% | VIP -7%, +0,3 pp atrasados |
| 2 | 15,5% (-54%) | +20,2% (limite é 20%) | VIP -15%, +1,25 pp atrasados |
| 3 | 9,0% (-73%) | +36,6% | VIP -22%, +2,3 pp atrasados, P99 +14,7% |

O prazo virtual **protege VIPs de verdade em sobrecarga**, mas o ganho é pago em cauda (P99) e em atrasados gerais nos outros cenários. Como o grupo decidiu que VIP é critério secundário, o EDF fica. α = 2 em `overload_125` ficou na fronteira; vale revisitar se a prioridade do VIP voltar a pesar.

## Achados principais

1. **Atraso só aparece acima de ~110% de carga** (varredura `sweep_*`). Até 100% todas as estratégias têm 0% de atrasos; em 105% só FIFO (0,7%) e WSPT (2,3%) atrasam.
2. **Em sobrecarga (125%) o EDF quase não melhora o % de atrasados** sobre o FIFO (41,9% contra 43,7%): ao priorizar pedidos já vencidos, atrasa os demais (efeito dominó). Em compensação tem o **menor P99** (102 min contra 161 do FIFO).
3. **`two_queues` e WSPT parecem melhores em sobrecarga** (15,4% e 19,3% atrasados) **porque abandonam pedidos**: P99 de 616 e 704 min. Não são alternativas boas.
4. **Docas especializadas custam em mix deslocado:** `mix_shift_33` tem 27% de atrasados com `base_15` contra 0% com `generic_15`; a classe Pesada fica a 100% de utilização com Express a 31%. O empréstimo de mão única não resolve (só ajuda classes menores). Em `overload_125` a diferença é pequena (41,9% contra 40,3%).
5. **Empréstimo:** quase irrelevante em % de atrasados, mas aumenta a vazão em carga alta (484 contra 471 pedidos/h em `peak_105`).
6. **Algoritmo de ordenação:** o heap vence em custo com resultados idênticos (0 divergências em 240 execuções). Em `overload_125`, EDF por pedido: heap 23 operações e 0,76 s de CPU; Insertion 216 e 1,2 s; Selection 341 e 2,2 s; Merge 1.519 e 10 s; Quick (pivô fixo) 39.850 e 110 s. No benchmark isolado (fila de 10 mil): `pop` custa 0,023 ms no heap, 7,3 ms no Selection, 81 ms no Merge e ~11,9 s no Quick; Insertion tem `push` de 3 ms contra 0,004 ms do heap.

## Ressalvas (leia antes de citar números)

- **Cenários pouco discriminantes:** `normal_85`, `peak_105` e `dock_outage` ficaram com ~0% de atrasos. As janelas de 30 a 240 min são folgadas e os vales do perfil diário esvaziam a fila. O documento antigo (janelas de 30 a 120 min, 6,3% de atrasados no pico) não se reproduz aqui. Sugestão: encurtar as janelas (30 a 120 min) ou subir o `peak_105` para ~110% e rodar de novo.
- **`black_friday` com `generic_15` deu 36,5% de atrasados contra 11,0% das docas especializadas**, ao contrário do esperado e do que ocorre em `mix_shift_33`. Não investigamos a causa; trate como hipótese a verificar.
- **`throughput_per_h` é afetado pela cauda de esvaziamento** da fila no fim do dia (mede entre o fim do warm-up e a última conclusão); não compare com 480/h diretamente.
- **O α não foi calibrado em sementes separadas:** a grade de α foi avaliada nas sementes 0 a 29. Isso não altera o veredito EDF, mas a calibração formal ainda está pendente (`--calibration`, sementes 1000 a 1009).
- Benchmark do Quick em n = 50 mil foi pulado (projeção acima de 100 s).
- Dados sintéticos: o score é gerado de SLA, distância, valor e reputação e favorece quem o usa. Parâmetros dos concorrentes (faixa 30 min, aging 0,2, limite 60 min) não foram calibrados.

## Próximos passos
1. Encurtar janelas e/ou subir a carga de `peak_105` e repetir.
2. Investigar `black_friday` × `generic_15` e o uso da cauda no `throughput`.
3. Rodar a calibração de α em sementes separadas.
4. Teste A/B em região piloto (EDF contra o prazo virtual).
