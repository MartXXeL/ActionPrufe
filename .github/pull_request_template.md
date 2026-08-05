## Que cambia

<!-- Una frase. El detalle va en los commits. -->

## Por que

<!-- El problema que resuelve. Si es un fallo, que caso concreto se veia mal. -->

## Comprobado

- [ ] `ruff format --check . && ruff check .`
- [ ] `mypy`
- [ ] `pytest` (unitarias e integracion)
- [ ] Si cambia una regla de juicio, hay una prueba que fija el caso que la justifica
- [ ] Si cambia lo que se publica en motivos, logs o prompts, no se filtra nada sensible
