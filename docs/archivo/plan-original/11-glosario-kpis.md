# 11 — Glosario de KPIs con Interpretación de Negocio

**Este archivo es el insumo directo de la tabla `dim_metric` (Etapa 6) y del componente
`kpi_card` del dashboard (Etapa 8).** El agente debe cargarlo como datos, no reescribirlo.

Formato de cada entrada: qué es, fórmula, de dónde sale, qué significa que suba, qué
significa que baje, referencia de industria, y advertencias.

---

## Capacidad y demanda

### ASK / ASM — Available Seat Kilometers / Miles
**Qué es:** la capacidad que la aerolínea puso a la venta.
**Fórmula:** `asientos disponibles × distancia volada`, sumado sobre todos los vuelos.
**Fuente:** comunicado de resultados; derivable de BTS T-100 (`seats × distance`).
**Si sube:** la aerolínea está creciendo su oferta. Bueno **solo si** la demanda (RPK)
crece igual o más rápido; si no, el load factor cae y probablemente el yield también.
**Si baja:** contracción o disciplina de capacidad. En una industria con sobreoferta,
recortar capacidad suele **subir** los precios y el margen unitario. No es
automáticamente malo — de hecho, "disciplina de capacidad" es un elogio en el sector.
**Referencia:** Aeroméxico reportó ASMs -1.2% YoY en 1Q26 con ingresos +13.3%: eso es
precisamente la estrategia de precio sobre volumen.
**Advertencia:** ASK (km) ≠ ASM (millas). Factor: 1 milla = 1.609344 km.

### RPK / RPM — Revenue Passenger Kilometers / Miles
**Qué es:** la demanda efectivamente vendida.
**Fórmula:** `pasajeros de pago × distancia volada`.
**Fuente:** comunicado; derivable de T-100 (`passengers × distance`).
**Si sube:** más gente volando más lejos. Positivo, casi siempre.
**Si baja:** caída de demanda o de red.
**Advertencia:** solo cuenta pasajeros de pago; los pases de empleado y los premios de
lealtad suelen excluirse (varía por aerolínea — verificar la definición de cada una).

### Load Factor — Factor de ocupación
**Qué es:** qué porcentaje de los asientos ofrecidos se vendió.
**Fórmula:** `RPK / ASK`
**Fuente:** reportado directamente; también derivable.
**Si sube:** mejor utilización del activo. Cada avión que despega con más gente reparte
sus costos fijos entre más pasajeros.
**Si baja:** hay capacidad que se está desperdiciando.
**Referencia de industria:**
- ULCC (Ryanair, Wizz): **~90–96%**
- LCC (Volaris, Viva): **~85–90%**
- Network carrier (Aeroméxico, Delta): **~84–87%**
Aeroméxico: 84.4% en 1Q26 vs 82.3% en 1Q25.
**Advertencia clave:** un load factor alto **no** es bueno por sí solo. Se puede llenar
cualquier avión bajando el precio lo suficiente. Hay que mirarlo junto con el yield.
Un network carrier opera estructuralmente más bajo que un ULCC porque vende conexiones
y asientos premium que requieren dejar inventario disponible.

### Passengers — Pasajeros transportados
**Qué es:** conteo de pasajeros.
**Fuente:** comunicado, AFAC, T-100.
**Advertencia:** un pasajero con conexión puede contarse una o dos veces según la fuente.
AFAC y los reportes de la compañía pueden diferir por esto. **Nunca** mezclar fuentes
sin verificar la definición.

### Average Stage Length — Etapa promedio
**Qué es:** la distancia media de un vuelo de la aerolínea.
**Fórmula:** `ASK / asientos ofrecidos` (o `RPK / pasajeros`).
**Por qué es la métrica más importante que nadie mira:** **todas** las métricas
unitarias (RASK, CASK, yield) se mueven mecánicamente con ella. Los costos por vuelo
(despegue, aterrizaje, tripulación de cabecera, handling) se reparten entre más
kilómetros cuando la etapa es más larga → CASK baja sin que la aerolínea sea más
eficiente. Lo mismo con RASK.
**Ajuste (fórmula que publica Aeroméxico):**
```
SLA_RASK = RASK × (stage_length / 1834)^0.5
```
**Regla:** nunca comparar métricas unitarias entre aerolíneas sin ajustar por esto.

---

## Ingreso unitario

### RASK / RASM — Revenue per Available Seat Kilometer / Mile
**Qué es:** cuánto ingreso genera cada asiento-kilómetro ofrecido.
**Fórmula:** `ingreso total / ASK`
**Si sube:** la aerolínea está monetizando mejor su capacidad — sea por precio, por
mejor mix, por más ingreso auxiliar, o por más carga.
**Si baja:** presión de precios, exceso de capacidad, o mix desfavorable.
**Advertencia:** sube o baja mecánicamente con el stage length. Ajustar.

### TRASM — Total Revenue per ASM
**Qué es:** RASM incluyendo **todo** el ingreso (pasaje + carga + auxiliares + otros).
**Fuente:** Aeroméxico reporta 15.6¢/ASM en 1Q26.
**Por qué importa más que PRASM:** captura la capacidad de la aerolínea de generar
ingreso por vías distintas al boleto, que es donde está la batalla moderna del sector.

### PRASM — Passenger Revenue per ASM
**Qué es:** solo el ingreso de pasaje sobre la capacidad.
**Uso:** comparar TRASM contra PRASM revela cuánto pesa el ingreso no-boleto.

### Yield
**Qué es:** el precio promedio por kilómetro-pasajero vendido. Es el "precio unitario"
de la aerolínea.
**Fórmula:** `ingreso de pasaje / RPK`
**Si sube:** poder de precio, mejor mix (más premium, más business, menos promoción).
**Si baja:** guerra de precios, o la aerolínea está llenando aviones con tarifa baja.
**La relación clave:** `RASK ≈ Yield × Load Factor`. Un RASK plano puede esconder un
yield en caída compensado por un load factor en alza — y eso es una historia muy
distinta a un RASK plano con ambos estables. **El dashboard debe descomponerlo.**

---

## Costo unitario

### CASK / CASM — Cost per Available Seat Kilometer / Mile
**Qué es:** cuánto cuesta ofrecer un asiento-kilómetro.
**Fórmula:** `gastos operativos totales / ASK`
**Si sube:** presión de costos (combustible, salarios, mantenimiento, aeroportuarios)
o menor utilización.
**Si baja:** eficiencia, escala, o etapas más largas.

### CASK ex-fuel / CASM ex-fuel — **la métrica de eficiencia real**
**Qué es:** el costo unitario excluyendo combustible.
**Fórmula:** `(gastos operativos − gasto de combustible) / ASK`
**Por qué se excluye el combustible:** representa 20–40% del costo y su precio lo fija
el mercado, no la aerolínea. Aislarlo permite ver si la administración está haciendo
bien su trabajo en lo que **sí** controla.
**Si baja:** eficiencia estructural genuina. Es la métrica que más valoran los analistas.
**Si sube:** problema real de costos, salvo que se explique por etapas más cortas.
**Referencia:** Aeroméxico 10.2¢/ASM en 1Q26. El CASK global promedio rondaba
7.5¢/ASK en 2019; los ULCC operan sustancialmente por debajo de los network carriers,
por diseño (menos servicio, un solo tipo de avión, sin hub, sin conexiones).

### Spread RASK − CASK — el margen unitario (PASK)
**Qué es:** la diferencia entre lo que ingresa y lo que cuesta cada asiento-kilómetro.
**Por qué es LA métrica:** RASK o CASK por separado son media película. Una aerolínea
con CASK altísimo puede ser muy rentable si su RASK es aún más alto (Emirates), y una
con CASK bajísimo puede perder dinero si su RASK se derrumba. **Lo que importa es el
spread.**
**Si sube:** la aerolínea está ganando más por unidad de capacidad. Fin de la discusión.
**Referencia de margen:** 10–20% se considera fuerte para un LCC; 5–15% para un
full-service.
**En el dashboard:** debe ser la gráfica principal de la página de resumen, y debe
descomponerse en un waterfall (precio, combustible, eficiencia, FX).

### Break-even Load Factor
**Qué es:** qué porcentaje de ocupación necesita la aerolínea para cubrir sus costos.
**Fórmula:** `CASK / Yield`
**Si baja:** mayor resiliencia — la aerolínea aguanta una caída de demanda sin perder
dinero.
**Uso en el dashboard:** graficarlo contra el load factor real. La distancia entre
ambos es el **colchón de seguridad** de la aerolínea, y se explica solo visualmente.

---

## Rentabilidad

### EBITDAR ajustado
**Qué es:** utilidad antes de intereses, impuestos, depreciación, amortización y
**rentas de aeronaves**.
**Por qué la "R":** históricamente las aerolíneas arrendaban gran parte de su flota;
excluir la renta permitía comparar entre las que compran y las que arriendan.
**Advertencia importante (IFRS 16 / ASC 842):** desde la entrada de estas normas, los
arrendamientos van al balance como activo por derecho de uso y pasivo, y la renta se
convierte en depreciación + interés. Eso **cambió el significado del EBITDAR** y complica
la comparación con periodos anteriores y con empresas bajo la otra norma
(Delta, US-GAAP). **Declararlo en el dashboard.**
**Referencia:** Aeroméxico 335.8 mdd, margen 25.0% en 1Q26.

### Margen operativo
**Fórmula:** `utilidad operativa / ingreso total`
**Referencia:** Aeroméxico 10.6% en 1Q26. Un margen operativo de doble dígito en
aviación es sólido; la industria opera históricamente con márgenes delgados.

---

## Ingresos auxiliares y mix

### Ancillary Revenue Share
**Qué es:** qué proporción del ingreso viene de fuentes distintas al boleto (equipaje,
selección de asiento, prioridad, cambios, programa de lealtad, tarjetas cobranded).
**Fórmula:** `ingreso auxiliar / ingreso total`
**Por qué importa:** es el gran diferenciador del modelo ULCC y la fuente de ingreso
más rentable del sector (margen casi puro).
**Referencia (IdeaWorksCompany 2025 Yearbook, FY2024, 61 aerolíneas):**
- Frontier: **62.0%** (primera vez que alguien rompe el 60%)
- Spirit: **58.7%**
- **Volaris: 55.3%**
- Allegiant: **52.9%**
- El ancillary global superó **148,000 millones de dólares** en 2024
Los network carriers como Aeroméxico operan muy por debajo de estos niveles, por diseño:
su ingreso viene del boleto premium y de la conexión, no del desglose de servicios.
**Uso narrativo:** comparar Aeroméxico vs Volaris en esta métrica ilustra dos filosofías
de negocio opuestas en el mismo mercado.

---

## Operación y flota

### Fleet Size — Flota
**Qué es:** número de aeronaves en operación. Aeroméxico: 166 en 1Q26.
**Uso:** denominador de las métricas de productividad de activo.

### Aircraft Utilization — Utilización de flota
**Qué es:** horas de vuelo por avión por día.
**Si sube:** mejor amortización de un activo carísimo. Los ULCC maximizan esto
agresivamente (aviones en el aire 12+ horas/día).
**Si baja:** aviones parados = capital ocioso. Puede deberse a mantenimiento,
restricciones de slots, o problemas de la cadena de suministro (los motores GTF han
tenido a aviones en tierra en toda la industria).
**Advertencia:** un network carrier tiene utilización estructuralmente menor porque
opera bancos de conexión en su hub, lo que implica aviones en tierra esperando.

### ASM per Aircraft
**Fórmula:** `ASM / número de aviones`
**Uso:** proxy de productividad de flota cuando no se publica la utilización en horas.

### OTP — On-Time Performance / Puntualidad
**Qué es:** porcentaje de vuelos que llegan dentro de la ventana de puntualidad
(típicamente 15 minutos).
**Por qué importa comercialmente:** correlaciona con satisfacción, con costo (las
irregularidades son carísimas: reacomodo, hoteles, compensaciones) y con la capacidad
de vender conexiones confiables.
**Referencia:** **Aeroméxico fue nombrada la aerolínea más puntual del mundo por Cirium
en 2024 y 2025** (segundo año consecutivo), y lideró también en 1Q26. Es un activo
competitivo real y una parte importante de la narrativa del dashboard.

---

## Mercado y competencia

### Market Share doméstico
**Fórmula:** `pasajeros de la aerolínea / pasajeros totales del mercado` (fuente: AFAC)
**Advertencia:** decidir si "Aeroméxico" incluye Aeroméxico Connect. AFAC los reporta
separados; los financieros consolidan. **Ser consistente y declararlo.**

### HHI — Índice de concentración de la red
**Fórmula:** `Σ (share_ruta_i)²`
**Uso:** mide qué tan dependiente es la aerolínea de pocas rutas o de un solo hub.
Un HHI alto significa concentración → mayor exposición a un choque localizado
(ej. saturación del AICM).

---

## Costo de combustible

### Fuel Cost Share
**Fórmula:** `gasto de combustible / gasto operativo total`
**Referencia:** típicamente 20–40% según el precio del crudo. Es el termómetro de la
exposición de la aerolínea.

### Elasticidad al jet fuel
**Qué es:** cuánto sube el CASM cuando sube 1% el precio del jet fuel.
**Cálculo:** regresión del CASM contra el precio del jet fuel (US Gulf Coast, EIA/FRED),
con rezagos.
**Uso en el dashboard:** escenarios. "Si el jet fuel sube 20%, el margen operativo cae
X puntos, todo lo demás constante."

---

## Notas transversales para `dim_metric`

Al poblar la tabla, respetar:

1. **`higher_is_better` no siempre es booleano.** Para load factor y ASK depende del
   contexto. Usar `NULL` y explicar en `caveats`.
2. **Toda métrica unitaria lleva la advertencia de stage length** en `caveats`.
3. **Toda métrica comparada entre aerolíneas lleva la advertencia de norma contable**
   (IFRS vs US-GAAP) y de año fiscal (Ryanair).
4. **Los benchmarks de industria son aproximados** y varían por fuente, año y definición.
   Presentarlos como referencia, no como umbral.
5. Los textos de `business_interpretation_*` van en **español, en segunda persona neutra
   y sin jerga**. Deben ser comprensibles para alguien que no conoce el sector.
