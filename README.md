# VelozMart MPS: Marketplace Priority Sorter

Projeto final do Coding Tank (Ordenação e Prioridade). Compara estratégias de ordenação da fila de expedição de uma grande empresa de logística e varejo da América Latina, com **docas especializadas por tamanho** (Express, Padrão, Pesada).

Algoritmo final **ainda não escolhido**: os finalistas são **EDF** e **prazo virtual** (`prazoAbs - α·score`). A escolha sai da simulação, com o critério da seção 5.3 de `docs/VelozMart_MPS_Especificacao_e_Plano_de_Testes.pdf`.

## Estrutura
```
configs/      docas, estratégias e cenários
docs/         contrato entre módulos, especificação (PDF)
mps/models.py          modelos compartilhados
mps/datagen/           gerador de dados sintéticos (cenários realistas)
mps/strategies/        as 7 estratégias de chave (FIFO, EDF, composto, duas filas, faixas+aging, WSPT, prazo virtual)
mps/sim/               simulador de eventos discretos + captura de métricas
analysis/              análise, gráficos e relatório
tests/                 testes (unittest)
```

## Uso (da raiz do repositório)
```
python -m mps.datagen --scenarios all --seeds 0-29 --out data/synthetic
python -m mps.sim --data data/synthetic --out results --scenarios all --strategies all --docks base_15 --seeds 0-29 --workers 4
python analysis/analyze.py --results results --out results/report
python -m unittest discover -s tests -v
```
Análise: `pip install -r requirements.txt` (de preferência em `.venv`).

Experimento v2 (janelas apertadas e 5 configurações de docas):
```
python -m mps.datagen --scenarios all --seeds 0-29 --window-profile tight --out data/synthetic_tight
python -m mps.datagen --scenarios all --calibration --window-profile tight --out data/synthetic_tight
bash scripts/run_experiments_v2.sh
python analysis/analyze.py --results results/v2 --out results/v2/report
```

Resultados versionados em `reports/` (ver `reports/v0.3.0/ANALISE.md`).

Ver `docs/CONTRACT.md` (formatos e regras), `docs/DOCKS.md` (modelos de docas) e `CONTRIBUTING.md` (git).
