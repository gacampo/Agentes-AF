# CATÁLOGO QA — AGENTES-AF · v1.4

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
| QA-11 | Sesgo | ¿El consenso de analistas se usa como dato, se reconcilia explícitamente su horizonte (normalmente 12 meses) contra los horizontes de 5/10 años de los escenarios propios, y se explica el desvío? | ADVERTENCIA | ASTS S3 / CSU-BN ago-2026 |
| QA-12 | Sesgo | Cambio >0.5 pts: ¿hay 2+ hechos nuevos verificables? | BLOQUEANTE | ASTS S4 |
| QA-13 | Sesgo | ¿Se nombró la evidencia contraria encontrada? | ADVERTENCIA | ASTS S5 |
| QA-14 | Datos | ¿TODO el análisis (todos los agentes) usa el precio actual post-split provisto, sin citar precios stale/pre-split en ningún agente? | BLOQUEANTE | BN split |
| QA-15 | Coherencia | ¿Las afirmaciones cualitativas de valoración (descuento/premium, barato/caro, margen de seguridad) son coherentes con la aritmética? (Ej: no decir "descuento al NAV" cuando precio > NAV-mid.) | BLOQUEANTE | BN arit |
| QA-16 | Datos | ¿Cada persona nombrada en un rol ejecutivo/directivo tiene ese rol confirmado por una búsqueda dedicada a "cambios de management" reciente (no solo asumido por conocimiento previo)? | BLOQUEANTE | BRKB Combs |
| QA-17 | Metodología | En el escenario conservador/pesimista, ¿los múltiplos y tasas de crecimiento usados están POR DEBAJO del rango histórico normal citado en el propio documento (no solo en el piso de ese rango)? | ADVERTENCIA | BRKB mult |
| QA-18 | Metodología | Si la empresa es un holding/conglomerado/trust con NAV o valor intrínseco autoevaluado por la propia compañía (ej. "Plan Value", book value, SOTP), ¿algún escenario —incluido el optimista— asume que el mercado paga el 100% o más de esa cifra SIN evidencia concreta de que el descuento histórico de esa empresa (o de un catalizador comparable ya ejecutado, ej. un spin-off previo) cerró de forma sostenida? | BLOQUEANTE | BN holdco ago-2026 |

## Changelog
- v1.0: catálogo inicial, 13 checks (origen WOSG + ASTS).
- v1.1: agrega QA-14 (precio de mercado actual provisto por el usuario, BLOQUEANTE).
- v1.2: reformula QA-14 (base del precio en todos los agentes); agrega QA-15 (coherencia aritmética de valoración, BLOQUEANTE).
- v1.3: agrega QA-16 (management desactualizado pese a web search, BLOQUEANTE) y QA-17 (escenario conservador insuficientemente conservador, ADVERTENCIA), origen BRKB.
- v1.4: agrega QA-18 (descuento de holding no debe asumirse cerrado en ningún escenario sin evidencia, BLOQUEANTE); reformula QA-11 para exigir reconciliación explícita de horizonte (12 meses del consenso vs. 5/10 años de los escenarios propios), origen BN ago-2026.
