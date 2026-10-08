# Captura internacional de mayo a julio de 2026

Fecha: 23 de septiembre de 2026.
Alcance: capturar mayo, junio y julio con el mismo diseño que abril, pasar
cada mes por la puerta, ajustar y generar su vista de revisión.
Autorización: explícita del operador para gastar hasta 4,812 unidades y para
fusionar los PR previos (#41 público, #14 privado).
Estado: **cuatro meses capturados y ajustados, sin publicar.** Nada toca el
dashboard, `flight_evidence_v1` ni el Analysis Agent.

Detalle técnico vigente: documento canónico §9.11–9.12.

## Gasto

| Mes | Núcleo | Resto | Total |
|---|---:|---:|---:|
| 2026M05 | 744 | 868 | 1,612 |
| 2026M06 | 720 | 868 | 1,588 |
| 2026M07 | 744 | 792 + 76 tras un 502 del proveedor | 1,612 |
| **Total** | | | **4,812** |

La reanudación de julio compró solo las 38 ventanas que faltaban; las 396 en
caché no se volvieron a comprar. Con abril (1,588), la serie internacional
suma 6,400 unidades.

## Resultado

Los cuatro meses dan `review` sin rechazos y convergen (500–652
iteraciones, desviación máxima ≤ 5 pasajeros). Grupo Aeroméxico estimado:
682,823 (abr), 684,480 (may), 679,144 (jun), 815,888 (jul), contra 686,694,
688,307, 681,986 y 819,374 que AFAC publica para Aerovías + Connect. Contraste
contra T-100: abril 6.3 %, mayo 5.7 % (Aerovías + Connect 6.9 % y 6.3 %);
junio y julio aún no tienen T-100.

## Lo que julio destapó

Con el tope individual por capacidad, julio no convergía: World2Fly, vista
solo en el sentido Madrid→Cancún, absorbía la ruta y dejaba sin lugar a Air
Europa y Evelop. Se sustituyó por una comprobación de **factibilidad
conjunta** con flujo máximo (Dinic, sin dependencias nuevas) que reduce
proporcionalmente al grupo en conflicto, precedida de un equilibrio global
de las marginales (las aerolíneas llevan pasajeros en rutas no cubiertas).
Ahora solo TUI Airways, Aerus y, en julio, World2Fly quedan topadas. Los
cuatro meses se reajustaron con la regla nueva.

La vista de revisión también se ajustó: la bandera de pasajeros sin asignar
se activa a partir del 1 % del total de la ruta, porque la columna tiene
soporte en todas las rutas y siempre guarda una fracción.

## Qué sigue

1. Revisión humana de las cuatro vistas antes de cualquier integración.
2. Cuando llegue T-100 de junio y julio, correr el contraste de esos meses
   (no requiere API).
