# Fluxo de trabalho (git)

## Branches
- `main`: sempre estável (testes passando). Sem commits diretos depois do commit inicial.
- `feat/<assunto>`, `fix/<assunto>`, `docs/<assunto>`, `chore/<assunto>`: trabalho em andamento, uma branch por módulo.
- Integração: merge com `--no-ff` em `main` depois de `python -m unittest discover -s tests -v` passar.
- Releases marcadas com tag semântica anotada (`v0.1.0`...).

## Commits (Conventional Commits)
`tipo(escopo): resumo no imperativo, até 72 caracteres`

Tipos: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `chore`, `build`.
Escopos: `datagen`, `strategies`, `sim`, `analysis`, `contract`, `configs`.
Exemplos: `feat(strategies): add EDF with id-to-position heap`, `test(datagen): check VIP fraction per scenario`.

- Commits pequenos e coesos (uma ideia por commit); corpo explica o porquê quando não é óbvio.
- Nunca comitar dados gerados (`data/synthetic/`), resultados (`results/`) nem `.venv/`; eles são reproduzíveis por script.
- Toda mudança em `docs/CONTRACT.md` ou `configs/` compartilhados vai em commit separado e é avisada aos outros módulos.

## Reprodutibilidade
Tudo que gera dados ou resultados é determinístico por seed. Registre o commit usado em `results/runs.meta.json`.
