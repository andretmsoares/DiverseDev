# Changelog

Formato baseado em Keep a Changelog; versões semânticas.

## [1.0.0] - 2026-11-11
- Análise geral consolidando os dois experimentos (34.380 execuções): nota ponderada por estratégia, melhor algoritmo no geral, por tipo de docas e na Black Friday, sensibilidade ao peso do VIP.
- `analysis/overall.py` gera gráficos, HTML e PDF; resultados em `reports/v1.0.0`.

## [0.3.0] - 2026-11-10
- Perfil de janelas apertadas (`--window-profile tight`), modelos de docas não especializadas (`generic_nested_15`, `generic_speed_15`) e comparação completa de configurações de docas.
- Análise: veredito por configuração de docas, calibração de alpha, mapa estratégia × doca.
- Resultados em `reports/v0.3.0`.

## [0.2.0] - 2026-11-10
- Primeiros resultados completos (`reports/v0.1.0`), janelas amplas.

## [0.1.0] - 2026-11-10
- Gerador de dados sintéticos, sete estratégias, cinco backends de ordenação, simulador e script de análise.

## [0.0.1] - 2026-11-10
- Esqueleto do repositório, contrato entre módulos, configs de docas e estratégias.
