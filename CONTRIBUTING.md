# Contribuir

Gracias por mirar. Esto es una libreria pequena con una idea muy concreta detras, asi
que lo mas util antes de escribir codigo es entender cual es.

## La idea que hay que respetar

ActionPrufe comprueba **que el efecto observado es el efecto pretendido**. Todo lo demas
es accesorio. Dos consecuencias practicas para cualquier cambio:

1. **Ante la duda, no se aprueba.** Un veredicto que no se puede justificar es
   `AMBIGUOUS`, y la politica por defecto lo rechaza. Nunca conviertas un caso dudoso en
   `MATCH` para que pase una prueba.
2. **La IA no decide, desempata.** Si el diff ya demuestra el acierto o el fallo, no se
   llama a ningun modelo. Y su respuesta es binaria: todo lo que no sea un si limpio es
   un no.

## Antes de abrir un pull request

```bash
pip install -e ".[dev]"
python -m playwright install chromium

ruff format --check . && ruff check .
mypy
pytest
```

Los tres tienen que estar en verde. Es lo mismo que ejecuta el CI.

## Como se escriben las pruebas aqui

Cada prueba fija **un caso concreto que se ha visto fallar en automatizacion real**, y
su nombre lo dice en castellano. Si anades una regla de juicio, anade tambien el caso
que la justifica; y si el caso necesita una pagina que se porte mal, va en
`tests/fixtures/` con un comentario arriba explicando que simula y por que importa.

Las pruebas del nucleo no arrancan navegador: viven en `tests/unit` y corren en
centesimas sobre estados sinteticos. Solo baja a `tests/integration` lo que de verdad
necesita un navegador de por medio.

## Estilo

- El codigo y los comentarios van en castellano, sin acentos en el codigo fuente.
- Los comentarios explican **por que**, no que. Si un comentario repite lo que dice la
  linea siguiente, sobra.
- `ruff` decide el formato. No discutas con el.

## Seguridad

Si encuentras una forma de que datos sensibles salgan de la pagina, o de que una web
hostil provoque un comportamiento que no deberia, no abras una incidencia publica: lee
[SECURITY.md](SECURITY.md).
