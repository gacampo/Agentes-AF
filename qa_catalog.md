# CATÁLOGO QA — AGENTES-AF · v1.0

## Severidad
- BLOQUEANTE: una falla impide aprobar la tesis.
- ADVERTENCIA: se documenta y debe reconocerse, pero no bloquea.

## Checks vigentes
| ID | Categoría | Check (binario) | Severidad | Origen |
|----|-----------|-----------------|-----------|--------|
| QA-01 | Completitud | ¿Están los 9 agentes documentados? | BLOQUEANTE | WOSG H1 |
| QA-02 | Datos | ¿Toda cifra tiene fuente o derivación? | BLOQUEANTE | WOSG H6 |
| QA-03 | Datos | ¿Hay nombres de otras empresas del portafolio en el texto? | BLOQUEANTE | WOSG H2 |
| QA-04 | Metodología | ¿El rating está separado en Calidad y Valoración? | BLOQUEANTE | Protocolo |
| QA-05 | Metodología | ¿El rating lleva timestamp y precio de referencia? | BLOQUEANTE | Protocolo |
| QA-06 | Coherencia | ¿El rating es coherente con los red flags listados? | ADVERTENCIA | WOSG H4 |
| QA-07 | Riesgo | ¿Cada riesgo material está como probabilidad × impacto? | ADVERTENCIA | WOSG H3 |
| QA-08 | Riesgo | ¿El riesgo de persona clave tiene peso explícito? | ADVERTENCIA | WOSG H5 |
| QA-09 | Sesgo | Si cambió el rating, ¿hay dato nuevo (no solo pushback)? | BLOQUEANTE | ASTS S1 |
| QA-10 | Sesgo | Si el rating se movió igual que el precio reciente, ¿está justificado? | ADVERTENCIA | ASTS S2 |
| QA-11 | Sesgo | ¿El consenso se usa como dato y se explica el desvío? | ADVERTENCIA | ASTS S3 |
| QA-12 | Sesgo | Cambio >0.5 pts: ¿hay 2+ hechos nuevos verificables? | BLOQUEANTE | ASTS S4 |
| QA-13 | Sesgo | ¿Se nombró la evidencia contraria encontrada? | ADVERTENCIA | ASTS S5 |

## Changelog
- v1.0: catálogo inicial, 13 checks (origen WOSG + ASTS).
