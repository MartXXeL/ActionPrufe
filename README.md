# ActionProof

[![Tests](https://github.com/MartXXeL/ActionPrufe/actions/workflows/tests.yml/badge.svg)](https://github.com/MartXXeL/ActionPrufe/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/python-3.12+-blue)
![Playwright](https://img.shields.io/badge/playwright-1.49+-green)
![Licencia](https://img.shields.io/badge/licencia-MIT-lightgrey)

**Comprueba que cada accion de navegador hizo lo que pretendia — y la deshace si no.**

Un agente hace clic en «Anadir Camiseta M». Playwright no da error. El carrito acaba
con un pantalon. Nadie se entera hasta tres pasos despues, cuando ya es tarde para
deshacerlo.

Eso no es un selector roto: es un **efecto equivocado**, y hoy nadie lo comprueba.
Los *healer agents* reparan selectores que ya no encuentran nada. Los frameworks de
agentes clican y confian. ActionProof hace la pregunta que falta: *¿lo que cambio en
la pagina es lo que yo queria cambiar?*

```python
from playwright.async_api import async_playwright
from actionproof import ActionProof, VerificationFailed

ap = ActionProof(page)

# Verificacion automatica: no hay que declarar nada.
await ap.click(page.get_by_role("button", name="Anadir Camiseta M"))

# Y si quieres afinar, declara la intencion.
await ap.click(
    page.get_by_role("button", name="Anadir Camiseta M"),
    intent="el carrito suma una camiseta talla M",
)
```

Si el efecto no corresponde al objetivo, ActionProof **lo deshace y reintenta**. Si no
puede deshacerlo, **aborta** en vez de seguir operando sobre un estado que ya no es el
que se creia.

## Como funciona

```
estabilizar -> leer objetivo -> actuar -> estabilizar -> diferenciar -> juzgar
                                                                          |
                        match <-------------------------------------- veredicto
                                                                          |
                                      deshacer y reintentar <--------- mismatch
                                                                          |
                                                 abortar <--- sin inversa posible
```

### 1. Identidad semantica, no posicion en el DOM

El fallo que perseguimos nace de que **React recicla nodos**. Entre que localizas un
elemento de una lista virtualizada y que lo clicas, ese nodo puede representar ya otra
cosa. Identificar por ruta, por handle o por indice es identificar por algo que ya
cambio.

Aqui la identidad de un elemento es `(rol, nombre accesible, region)` — lo que un
humano percibiria. Un reordenamiento de la lista no produce ninguna diferencia; una
sustitucion de contenido, si.

### 2. Estabilizacion antes de juzgar

Sin esperar a que la pagina se asiente no se puede distinguir «la accion no hizo nada»
de «la accion aun no ha hecho nada». ActionProof espera a que dos lecturas consecutivas
coincidan, y si se agota el tiempo con la pagina todavia mutando **lo dice**: un diff
vacio sobre una pagina inestable es `AMBIGUOUS`, nunca `MISMATCH`.

### 3. Juicio deterministico primero

El veredicto sale del diff siempre que se pueda:

| Situacion | Veredicto |
|---|---|
| El efecto se atribuye al objetivo | `MATCH` |
| El efecto corresponde a otro elemento de la misma lista | `MISMATCH` |
| Se conmuto la casilla de al lado | `MISMATCH` |
| El texto entro en otro campo | `MISMATCH` |
| Se marco la correcta **y ademas** otra | `MISMATCH` |
| No paso nada y la pagina estaba estable | `MISMATCH` |
| Paso algo sin relacion clara con el objetivo | `AMBIGUOUS` |

### 4. La IA solo desempata, y solo dice si o no

`AMBIGUOUS` es la unica puerta por la que entra un modelo. Y su respuesta es binaria:
cualquier cosa que no sea un «SI» limpio —un «podria», una respuesta vacia, un error de
red— se lee como **NO**. Ante la duda, la accion no se da por buena. El arbitro es
opcional: sin el, la politica configurable decide (`reject` por defecto).

### 5. Deshacer de verdad, o parar

Las inversas se intentan en orden: reescribir el valor previo, volver a conmutar,
buscar en la pagina el control de retirada que aparecio («Quitar», «Eliminar», «×»),
volver atras en el historial. Despues se **comprueba que el efecto se retiro**; si
queda residuo, es `UndoFailed`. Si no hay inversa aplicable, es `IrreversibleAction`.
En ninguno de los dos casos se continua.

## Instalacion

```bash
pip install -e ".[dev]"          # desarrollo
pip install -e ".[ai]"           # con arbitro de Gemini
python -m playwright install chromium
```

## API

| Metodo | Que verifica |
|---|---|
| `click(target, intent=...)` | Que el efecto es atribuible a ese elemento |
| `fill(target, value, intent=...)` | Que el valor acabo en ese campo y no en otro |
| `check` / `uncheck(target)` | Que se conmuto ese elemento y **solo** ese |
| `select_option(target, label)` | Que la opcion elegida es la pedida |
| `settle()` | Espera a que la pagina deje de moverse |

Todas devuelven un `Result` con el veredicto, el motivo legible, el diff completo, los
intentos y cuantas veces hubo que deshacer. Los fallos se lanzan como
`VerificationFailed`, `UndoFailed` o `IrreversibleAction`.

### Ajustes

```python
ActionProof(
    page,
    ai_judge=GeminiJudge(api_key),  # opcional
    ambiguous="reject",             # "accept" si prefieres no bloquear
    max_attempts=2,
    quiet_ms=250,
    timeout_ms=5_000,
)
```

### Marcar regiones a mano

Si la pagina no tiene landmarks, `data-ap-region` y `data-ap-watch` permiten declarar
que zonas importan:

```html
<div data-ap-region="carrito">...</div>
<span data-ap-watch>Total: 49,90 €</span>
```

## Desarrollo

```bash
ruff check . && ruff format --check .
pytest                            # todo
pytest tests/unit                 # nucleo, sin navegador, centesimas
pytest -m browser                 # solo contra paginas reales
```

Las paginas de `tests/fixtures/` se portan mal a proposito:

| Pagina | Que simula |
|---|---|
| `virtualized.html` | La lista rota sus datos en `pointerdown`, asi que el clic acaba en el vecino |
| `late.html` | El efecto tarda 700 ms, como una respuesta de red lenta |
| `honest.html` | Todo correcto, para comprobar que no se inventan fallos |

## ToDo

### v0.1 — nucleo (en curso)
- [x] Identidad semantica estable frente a reciclado de nodos
- [x] Estabilizacion con deteccion de pagina inestable
- [x] Diff semantico por multiconjunto
- [x] Juicio deterministico: clic, fill, conmutacion y seleccion
- [x] Deteccion del vecino que se queda el clic
- [x] Arbitro de IA opcional con veredicto binario
- [x] Inversas y verificacion de que el efecto se retiro
- [x] API publica `ActionProof`
- [x] Pruebas del nucleo sin navegador
- [x] Paginas de prueba hostiles (lista virtualizada que recicla nodos, efecto tardio)
- [x] Pruebas de integracion con navegador real
- [x] CI en GitHub Actions
- [ ] Pagina de prueba con overlay que se queda los clics
- [ ] Pagina de prueba con confirmacion modal intermedia

### v0.2 — cobertura real
- [ ] Acciones pendientes: `hover`, `press`, `drag_and_drop`, `upload`
- [ ] Trazas: exportar cada accion con su pre-estado, post-estado, diff y veredicto
- [ ] Diagnostico legible cuando falla (que se esperaba, que paso, que se deshizo)
- [ ] Soporte de `iframe` y de shadow DOM
- [ ] Cache del snapshot para no re-evaluar la pagina entera en paginas grandes

### v0.3 — adopcion
- [ ] Integracion con `browser-use` como capa de verificacion
- [ ] Modo *observador*: verificar sin deshacer, para auditar un agente ajeno
- [ ] Banco de pruebas reproducible con tasa de fallos detectados
- [ ] Publicacion en PyPI

## Licencia

MIT.
