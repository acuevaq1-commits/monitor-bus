# Especificación funcional y técnica — Monitor del Bus de Integraciones

## 1. Objetivo

Construir una aplicación web para monitorear el flujo de integraciones entre Banner 9, el bus de integración y SAP Cloud. El sistema deberá detectar fallas técnicas, funcionales y de calidad de datos; visualizar el estado operativo en tiempo real; analizar inconsistencias en payloads; administrar reglas de monitoreo; y preparar la base para alertas automáticas.

La aplicación deberá consultar principalmente estas tablas existentes:

- `iislog.iis_run`: ejecuciones, lotes, contadores, estados, errores y payloads.
- `iislog.iis_event`: eventos técnicos y funcionales asociados a una ejecución.
- `iislog.dq_issue`: incidencias de calidad de datos.
- `iisupao.plantilla_integracion`: catálogo y configuración de las integraciones.

## 2. Alcance inicial

El primer alcance incluye:

1. Dashboard ejecutivo y operativo.
2. Detalle y trazabilidad de ejecuciones.
3. Catálogo de 21 categorías de fallas.
4. Análisis de inconsistencias en payloads para:
   - `00021`: Business Partner SAP.
   - `00022`: pedidos de ventas.
   - `00023`: pagos y compensaciones.
5. Consulta de eventos y problemas de calidad.
6. Formularios mantenedores para reglas, umbrales, catálogos y configuración.
7. Base funcional para alertas posteriores.

No se incluye inicialmente la administración directa de RabbitMQ, SAP CPI ni servidores. Sus métricas podrán incorporarse en una fase posterior.

## 3. Stack tecnológico propuesto

### Backend

- Python 3.12 o superior.
- FastAPI.
- SQLAlchemy 2.x para acceso a datos.
- Psycopg 3 para PostgreSQL.
- Pydantic 2 para validación y configuración.
- Alembic para migraciones de tablas propias del monitor.
- APScheduler o Celery para evaluaciones periódicas de reglas.
- Pytest para pruebas unitarias y de integración.

### Interfaz web

- Jinja2 para plantillas HTML.
- HTMX para filtros, tablas y actualizaciones parciales sin recargar toda la página.
- Bootstrap 5.3 para diseño visual responsivo.
- Bootstrap Icons.
- ApexCharts para series de tiempo, barras, dona y heatmaps.
- DataTables para tablas con filtros, paginación y exportación.

### Lineamientos visuales

- Diseño limpio, corporativo y responsivo.
- Menú lateral fijo y plegable.
- Barra superior con rango temporal, ambiente, estado general y usuario.
- Fondo gris muy claro; cards blancas con bordes suaves y sombra discreta.
- Colores semánticos consistentes:
  - Verde: normal o exitoso.
  - Amarillo: advertencia.
  - Naranja: degradación o error parcial.
  - Rojo: error crítico.
  - Gris: sin datos o no evaluado.
  - Azul: información y navegación.
- Modo claro como predeterminado y modo oscuro opcional.
- Toda fecha deberá mostrarse en la zona horaria `America/Lima`.

## 4. Arquitectura del sistema

Aplicar Clean Architecture, manteniendo el dominio independiente de FastAPI, SQLAlchemy y PostgreSQL.

```text
src/
├── domain/
│   ├── entities/
│   │   ├── integration_run.py
│   │   ├── integration_event.py
│   │   ├── data_quality_issue.py
│   │   ├── integration_template.py
│   │   ├── monitoring_rule.py
│   │   ├── detected_incident.py
│   │   └── payload_inconsistency.py
│   ├── enums/
│   │   ├── severity.py
│   │   ├── incident_status.py
│   │   └── failure_category.py
│   ├── repositories/
│   │   ├── run_repository.py
│   │   ├── event_repository.py
│   │   ├── dq_repository.py
│   │   ├── template_repository.py
│   │   └── rule_repository.py
│   └── services/
│       ├── rule_evaluator.py
│       ├── payload_validator.py
│       └── severity_calculator.py
├── application/
│   ├── dto/
│   ├── use_cases/
│   │   ├── get_dashboard_summary.py
│   │   ├── search_runs.py
│   │   ├── get_run_trace.py
│   │   ├── detect_failures.py
│   │   ├── analyze_payload.py
│   │   ├── manage_rules.py
│   │   └── acknowledge_incident.py
│   └── ports/
│       ├── clock.py
│       └── notifier.py
├── infrastructure/
│   ├── database/
│   │   ├── models/
│   │   ├── repositories/
│   │   ├── session.py
│   │   └── queries/
│   ├── schedulers/
│   ├── notifications/
│   └── settings.py
├── presentation/
│   ├── api/
│   ├── web/
│   │   ├── routes/
│   │   ├── templates/
│   │   └── static/
│   └── dependencies.py
└── main.py

tests/
├── unit/
├── integration/
└── functional/
```

### Reglas de dependencia

- `domain` no debe importar FastAPI, SQLAlchemy ni componentes de infraestructura.
- `application` coordina casos de uso mediante interfaces del dominio.
- `infrastructure` implementa repositorios y conexiones externas.
- `presentation` expone rutas web y API, sin contener reglas de negocio.
- Las consultas SQL optimizadas pueden ubicarse en infraestructura, pero sus resultados deben convertirse a DTOs.

## 5. Diseño general de navegación

### Barra superior

Debe contener:

- Nombre del sistema: **Monitor de Integraciones Banner–SAP**.
- Selector de ambiente: Producción, Calidad o Desarrollo.
- Rango global de tiempo: última hora, 6 horas, 24 horas, 7 días, 30 días o personalizado.
- Indicador global: Operativo, Degradado o Crítico.
- Fecha y hora de última actualización.
- Botón de actualización manual.
- Activar/desactivar autoactualización.
- Menú de usuario.

### Menú lateral

```text
Inicio
├── Resumen general
├── Salud de integraciones
└── Actividad en tiempo real

Operación
├── Ejecuciones
├── Eventos
├── Calidad de datos
├── Incidentes detectados
└── Trazabilidad

Payloads
├── Inconsistencias
├── BP SAP — 00021
├── Pedidos de venta — 00022
└── Pagos — 00023

Análisis
├── Rendimiento
├── Reintentos y duplicados
├── Lotes y paginación
└── Tendencias

Configuración
├── Plantillas de integración
├── Reglas de monitoreo
├── Umbrales
├── Reglas de payload
├── Catálogos de errores
├── Ventanas de ejecución
└── Canales de alerta

Administración
├── Usuarios y roles
├── Auditoría
└── Estado del sistema
```

## 6. Pantalla principal

### 6.1 Filtros globales

- Rango de fechas.
- `pi_id`.
- Tipo de integración.
- Servicio.
- Host.
- Worker.
- Cola.
- Estado.
- Severidad.
- Sede, cuando esté disponible en el payload.

Los filtros deben afectar todos los indicadores y gráficos de la pantalla.

### 6.2 Indicadores superiores

Mostrar seis cards grandes:

1. **Integraciones activas**: plantillas activas con actividad esperada.
2. **Ejecuciones**: total del periodo.
3. **Tasa de éxito**: ejecuciones exitosas / ejecuciones finalizadas.
4. **Errores actuales**: errores sin resolver.
5. **Procesos bloqueados**: runs en `STARTED` por encima del umbral.
6. **Tiempo medio**: promedio y percentil 95 de duración.

Cada card debe incluir valor actual, comparación con el periodo anterior, color semántico y enlace al detalle filtrado.

### 6.3 Resumen gráfico

Incluir:

- Serie temporal de ejecuciones exitosas, fallidas y parciales.
- Barras por `pi_id` con total, éxito y error.
- Dona de distribución por estado.
- Top 10 de mensajes o códigos de error.
- Heatmap de errores por día y hora.
- Tabla de últimas ejecuciones críticas.

### 6.4 Cards de las 21 categorías de fallas

Mostrar una grilla responsiva de cards compactas. Cada card tendrá:

- Icono.
- Nombre de categoría.
- Total de hallazgos en el periodo.
- Cantidad crítica, alta y media.
- Tendencia frente al periodo anterior.
- Estado: normal, advertencia, crítico o sin datos.
- Fecha del último hallazgo.
- Enlace al listado filtrado.

Las 21 categorías son:

| N.º | Categoría | Ejemplos principales |
|---:|---|---|
| 1 | Ejecuciones fallidas | `FAILED`, `ERROR`, excepciones, errores parciales |
| 2 | Ejecuciones bloqueadas | `STARTED` antiguo, sin `finished_at`, worker detenido |
| 3 | Falta de ejecuciones | integración activa sin actividad dentro de su ventana |
| 4 | Red y conectividad | timeout, DNS, conexión rechazada, TLS, conexión reiniciada |
| 5 | HTTP y APIs | códigos 4xx/5xx, respuesta vacía o formato inválido |
| 6 | Errores funcionales SAP | rechazo funcional aun cuando HTTP fue exitoso |
| 7 | Calidad de datos | campos obligatorios, formatos, tipos y catálogos |
| 8 | Validación de esquema | incumplimientos de `pi_schema` |
| 9 | Transformación | pérdida de campos, conversión o mapeo incorrecto |
| 10 | Enrutamiento y colas | cola incorrecta, publicación o consumo fallido |
| 11 | Secuencia del flujo | etapa faltante entre BannerNexus, IISTransform e IISDispatcher |
| 12 | Duplicidad y reenvíos | documento, `corr_id` o payload procesado varias veces |
| 13 | Contadores inconsistentes | `ok_count + error_count <> executed`, totales inválidos |
| 14 | Lotes y paginación | página omitida o repetida, `batch_seq` discontinuo |
| 15 | Aplicación o worker | caída, reinicio, excepción o configuración inválida |
| 16 | Base de datos | conexión, bloqueo, deadlock, SQL u ORA error |
| 17 | Configuración | plantilla inexistente, inactiva o inconsistente |
| 18 | Trazabilidad del log | eventos huérfanos, `corr_id` ausente, run sin detalle |
| 19 | Rendimiento y capacidad | degradación de duración o throughput |
| 20 | Particiones y almacenamiento | falta de partición, disco, índices o retención |
| 21 | Fechas y tiempo | fechas negativas, futuras, zona horaria o reloj desfasado |

### 6.5 Priorización de las cards

- Ordenar primero las categorías críticas.
- Permitir fijar categorías favoritas.
- Permitir alternar entre vista de 21 cards y tabla compacta.
- Una categoría sin capacidad de medición debe indicar **Sin fuente de datos**, no cero errores.

## 7. Pantalla de ejecuciones

Tabla principal con:

- `ts`, `run_id`, `run_type`, `pi_id` y nombre de la integración.
- `service_name`, `worker_name`, `hostname`, `queue_name`.
- `corr_id`, `plan_id`, `batch_seq`, `ticket_id`, `pag`.
- `total`, `executed`, `ok_count`, `error_count`.
- Estado, duración, inicio y fin.
- Identificador de negocio extraído del payload.
- Indicador de severidad.
- Acciones: ver detalle, ver trazabilidad, analizar payload y copiar correlación.

Filtros rápidos:

- Solo fallidos.
- Solo bloqueados.
- Solo parciales.
- Solo con errores de payload.
- Solo duplicados.
- Solo sin `corr_id` válido.

### Detalle de ejecución

Usar pestañas:

1. Resumen.
2. Payload de entrada.
3. Payload transformado.
4. Respuesta SAP/CPI.
5. Eventos.
6. Problemas DQ.
7. Trazabilidad completa.
8. Incidentes detectados.

Los JSON deberán mostrarse con formato, plegado de nodos, búsqueda, copia y resaltado de diferencias. Los datos sensibles deberán enmascararse según configuración.

## 8. Pantalla de inconsistencias de payloads

Esta pantalla tendrá un resumen común y tres módulos especializados.

### 8.1 Resumen común

Cards:

- Payloads analizados.
- Payloads inconsistentes.
- Porcentaje de inconsistencia.
- Errores críticos.
- Campos más afectados.
- Integración más afectada.

Tabla de resultados:

- Fecha.
- `run_id`.
- `pi_id` y proceso.
- Identificador de negocio.
- Campo o ruta JSON.
- Valor encontrado.
- Regla incumplida.
- Severidad.
- Resultado SAP.
- Estado de revisión.
- Acciones.

Filtros:

- Tipo de integración.
- Regla.
- Campo JSON.
- Severidad.
- Estado de revisión.
- Resultado SAP.
- Rango de fechas.

### 8.2 BP SAP — `pi_id = '00021'`

Validaciones configurables sugeridas:

- Identificador Banner/BP obligatorio.
- Nombre o razón social obligatorio.
- Tipo de persona consistente con nombres y apellidos.
- Documento de identidad presente, válido y no duplicado.
- País, región, ciudad y código postal válidos.
- Correo con formato válido.
- Roles de BP requeridos.
- Sociedad y datos de cliente requeridos.
- Área de ventas existente: organización, canal y división.
- Moneda obligatoria donde corresponda.
- Valores de catálogo SAP válidos.
- BP enviado previamente con datos diferentes.
- Respuesta SAP sin `BusinessPartner`.
- Respuesta con mensajes tipo `E` o `A`.
- HTTP exitoso con rechazo funcional.

Identificadores sugeridos para búsqueda: `PARTNER`, `KUNNR`, PIDM, Banner ID, documento de identidad y Business Partner devuelto por SAP.

### 8.3 Pedidos de venta — `pi_id = '00022'`

Validaciones configurables sugeridas:

- `BSTKD` obligatorio y único según la regla de negocio.
- Fecha del pedido válida.
- Cliente/BP existente.
- Sociedad, organización de ventas, canal y división válidos.
- Moneda y tipo de cambio válidos.
- Material o concepto existente.
- Centro y almacén válidos cuando correspondan.
- Cantidad mayor que cero.
- Precio e importe válidos.
- Suma de posiciones consistente con la cabecera.
- Impuestos y descuentos dentro de las reglas.
- Posiciones duplicadas.
- Arreglo de posiciones vacío.
- Pedido reenviado después de haber sido creado.
- Respuesta SAP sin número de pedido.
- Diferencia entre `BSTKD` enviado y referencia devuelta.
- Mensajes SAP tipo `E` o `A`.

Identificadores sugeridos: `BSTKD`, número de pedido SAP, `PARTNER`, `KUNNR` y referencia Banner.

### 8.4 Pagos — `pi_id = '00023'`

Validaciones configurables sugeridas:

- Referencia de pago obligatoria y única.
- BP/cliente obligatorio.
- Sociedad y ejercicio válidos.
- Documento contable de referencia existente.
- Fecha de documento y contabilización válidas.
- Periodo contable abierto.
- Moneda obligatoria.
- Importe numérico y mayor que cero.
- Cuenta contable `HKONT` válida.
- Centro de costo u objeto de imputación cuando corresponda.
- Suma de posiciones balanceada.
- Pago duplicado.
- Pago parcial identificado correctamente.
- Compensación solicitada sin partidas compatibles.
- Respuesta sin `AccountingDocument`.
- Mensaje “No se compensó porque es un pago parcial”.
- HTTP exitoso con contabilización o compensación fallida.
- Documento ya compensado o revertido.

Identificadores sugeridos: referencia de pago, `HKONT`, `PARTNER`, documento contable, ejercicio y `AccountingDocument`.

### 8.5 Comparador visual

En cada hallazgo debe permitirse comparar:

- Payload original.
- Payload transformado.
- Payload enviado.
- Respuesta de CPI/SAP.

Las diferencias deben resaltarse por ruta JSON y clasificarse como campo agregado, eliminado, modificado o con tipo distinto.

## 9. Trazabilidad

La pantalla de trazabilidad mostrará una línea de tiempo agrupada por `corr_id`, identificador de negocio o `run_id`:

```text
BannerNexus → IISTransform → RabbitMQ → IISDispatcher → SAP CPI → SAP S/4HANA
```

Cada etapa mostrará:

- Inicio y fin.
- Estado.
- Duración.
- Host y worker.
- Cola.
- Cantidad de registros.
- Código HTTP o técnico.
- Resumen de error.
- Enlace al payload correspondiente.

Debe marcarse visualmente la etapa faltante, repetida, fuera de orden o excesivamente lenta.

## 10. Formularios mantenedores

### 10.1 Plantillas de integración

CRUD sobre `iisupao.plantilla_integracion`, respetando permisos:

- Código, nombre y descripción.
- Estado.
- Tipo de servicio.
- Sistemas de origen y destino.
- Cola.
- Número máximo de registros por petición.
- Esquema JSON.
- Datos y metadata.
- Reglas de validación y transformación.

Debe incluir validación previa del JSON y vista de solo lectura para producción si el usuario no tiene privilegios de edición.

### 10.2 Reglas de monitoreo

Campos sugeridos:

- Código y nombre.
- Categoría de falla.
- Descripción.
- `pi_id` específico o todos.
- Condición o tipo de evaluador.
- Parámetros JSON.
- Ventana de evaluación.
- Severidad.
- Frecuencia.
- Cantidad de ocurrencias antes de alertar.
- Periodo de silencio.
- Activa/inactiva.

No permitir SQL libre ingresado desde la interfaz. Las reglas deben elegir evaluadores seguros previamente implementados.

### 10.3 Umbrales

Configurar por integración:

- Duración máxima.
- Tiempo máximo en `STARTED`.
- Tiempo máximo sin actividad.
- Tasa mínima de éxito.
- Cantidad máxima de errores.
- Porcentaje máximo de errores DQ.
- Máximo de reintentos.
- Máximo de duplicados.
- Desviación permitida respecto del volumen histórico.

### 10.4 Reglas de payload

Campos:

- `pi_id`.
- Nombre de regla.
- Ruta JSON.
- Tipo de validación.
- Parámetros.
- Mensaje de error.
- Severidad.
- Aplica al payload de entrada, transformado, enviado o respuesta.
- Activa/inactiva.

Tipos de validación admitidos:

- Requerido.
- Tipo de dato.
- Longitud.
- Expresión regular.
- Rango.
- Catálogo.
- Unicidad.
- Comparación entre campos.
- Expresión funcional implementada en código.
- Presencia condicionada.

### 10.5 Catálogo de errores

- Código o patrón.
- Origen: aplicación, red, PostgreSQL, Oracle, RabbitMQ, CPI o SAP.
- Categoría.
- Severidad predeterminada.
- Descripción comprensible.
- Recomendación operativa.
- Responsable o equipo sugerido.
- Patrón de búsqueda seguro.
- Activo/inactivo.

### 10.6 Ventanas de ejecución

Permitir definir cuándo se espera actividad para cada `pi_id`:

- Días de la semana.
- Hora inicial y final.
- Frecuencia esperada.
- Tolerancia.
- Feriados o excepciones.
- Zona horaria.

Esta configuración es necesaria para detectar correctamente la falta de ejecuciones sin generar falsos positivos.

### 10.7 Canales de alerta

Dejar preparado el mantenimiento de:

- Correo.
- Microsoft Teams.
- Slack.
- Webhook.
- Alertas internas del sistema.

Campos: nombre, tipo, destinatarios, severidad mínima, horario, plantillas, activo y botón de prueba. Las credenciales no deberán mostrarse ni almacenarse en texto plano.

## 11. Modelo de datos adicional sugerido

Crear un esquema propio, por ejemplo `iismonitor`, sin modificar inicialmente las tablas productivas de logging.

### Tablas principales

- `monitoring_rule`: definición de reglas.
- `monitoring_threshold`: umbrales por integración.
- `execution_window`: ventanas esperadas.
- `payload_rule`: reglas de validación JSON.
- `error_catalog`: clasificación de errores.
- `detected_incident`: incidentes generados.
- `incident_occurrence`: ejecuciones vinculadas a un incidente.
- `incident_action`: reconocimiento, comentario, cierre o reapertura.
- `notification_channel`: configuración de canales.
- `notification_history`: envíos y resultados.
- `monitor_audit`: auditoría de cambios.

### Campos mínimos de `detected_incident`

- `incident_id`.
- `detected_at`.
- `last_seen_at`.
- `rule_id`.
- `category`.
- `severity`.
- `status`: abierto, reconocido, resuelto, silenciado.
- `pi_id`.
- `run_id` y `run_ts`, cuando correspondan.
- `corr_id`.
- `business_key`.
- `title`.
- `description`.
- `evidence_json`.
- `occurrence_count`.
- `assigned_to`.
- `acknowledged_at`.
- `resolved_at`.

Guardar `run_ts` junto con `run_id`, porque la clave primaria de `iis_run` es `(ts, run_id)`.

## 12. Reglas iniciales de detección

Implementar primero estas reglas por su alto valor operativo:

1. Run con `status` de error.
2. Run en `STARTED` por encima del umbral.
3. Integración activa sin actividad en su ventana.
4. `error_count > 0`.
5. `ok_count + error_count <> executed`.
6. `executed > total` o ejecución terminada con `executed < total`.
7. Evento con nivel `ERROR` y run no fallido.
8. Run fallido sin mensaje ni evento de error.
9. `corr_id` nulo, vacío o igual a `no-corr-id`.
10. Mismo identificador de negocio enviado repetidamente.
11. Timeout, DNS, conexión, TLS o HTTP 5xx.
12. HTTP exitoso con error funcional SAP.
13. Respuesta SAP sin identificador esperado.
14. `dq_issue` crítico.
15. Payload que incumple una regla configurada.
16. Evento o DQ huérfano.
17. `finished_at < ts`.
18. Degradación anormal del tiempo de ejecución.

## 13. API interna sugerida

```text
GET    /api/v1/dashboard/summary
GET    /api/v1/dashboard/failure-categories
GET    /api/v1/runs
GET    /api/v1/runs/{run_ts}/{run_id}
GET    /api/v1/runs/{run_ts}/{run_id}/trace
GET    /api/v1/events
GET    /api/v1/dq-issues
GET    /api/v1/incidents
POST   /api/v1/incidents/{id}/acknowledge
POST   /api/v1/incidents/{id}/resolve
GET    /api/v1/payload-inconsistencies
POST   /api/v1/payloads/analyze
GET    /api/v1/config/integration-templates
GET    /api/v1/config/rules
POST   /api/v1/config/rules
PUT    /api/v1/config/rules/{id}
GET    /api/v1/config/payload-rules
POST   /api/v1/config/payload-rules
PUT    /api/v1/config/payload-rules/{id}
```

Las rutas web HTML y las rutas API deberán compartir los mismos casos de uso.

## 14. Seguridad y auditoría

Roles sugeridos:

- **Consulta**: dashboards y detalles.
- **Operador**: reconoce y resuelve incidentes.
- **Analista**: administra reglas y umbrales.
- **Administrador**: configuración, usuarios y canales.

Requisitos:

- Integración futura con el SSO institucional.
- Control de acceso por rol.
- Auditoría de cambios de configuración.
- Protección CSRF en formularios.
- Consultas parametrizadas.
- Enmascaramiento de documentos, correos y otros datos personales.
- No registrar contraseñas, tokens, cookies ni cabeceras de autorización.
- Límites de tamaño para visualizar o descargar payloads.

## 15. Rendimiento de consultas

- Toda consulta sobre tablas particionadas debe filtrar por `ts`.
- Evitar consultas ilimitadas y aplicar paginación desde el servidor.
- Revisar índices de cada partición, no solamente los definidos con `ON ONLY` en la tabla padre.
- Eliminar índices funcionalmente duplicados después de validar su uso.
- Crear índices para las rutas JSON y filtros realmente utilizados.
- Considerar columnas generadas o una vista materializada para claves de negocio consultadas frecuentemente.
- Cachear resúmenes cortos del dashboard entre 15 y 60 segundos.
- Ejecutar el análisis pesado de payloads de forma asíncrona.
- No cargar `summary_json`, `context` ni `extra` en listados cuando no sean necesarios.

## 16. Experiencia de usuario

- Actualización automática configurable: 15 s, 30 s, 1 min o desactivada.
- Tooltips con explicación de cada métrica.
- Estados vacíos que expliquen si no hay errores o no existe fuente de datos.
- Skeleton loaders durante consultas.
- Toasts para operaciones de mantenimiento.
- Confirmación antes de desactivar reglas críticas.
- Exportación CSV/Excel en listados, respetando filtros y permisos.
- Enlaces profundos para compartir una búsqueda o ejecución específica.
- Persistencia de filtros favoritos por usuario.
- Accesibilidad: contraste AA, navegación por teclado y etiquetas descriptivas.

## 17. Pruebas y criterios de aceptación

### Pruebas

- Unitarias para cada evaluador de reglas y validador de payload.
- Integración para repositorios PostgreSQL.
- Funcionales para filtros, navegación y formularios.
- Casos con JSON incompleto, inválido, muy grande y con estructuras alternativas.
- Casos de zona horaria y cambios de día.
- Pruebas de rendimiento con periodos amplios y alto volumen.

### Criterios mínimos

- El dashboard carga el resumen del último día en menos de 3 segundos bajo carga normal.
- Las consultas siempre incluyen rango temporal.
- Cada card permite navegar hacia la evidencia que produjo el conteo.
- Una ejecución puede rastrearse por `run_id`, `corr_id` o identificador de negocio.
- Los payloads `00021`, `00022` y `00023` tienen reglas independientes y configurables.
- Ningún secreto aparece en pantalla, logs o respuestas API.
- Los estados sin fuente de datos no se presentan como cero.
- Las acciones de configuración quedan auditadas.

## 18. Fases de implementación

### Fase 1 — Base operativa

- Estructura Clean Architecture.
- Conexión de solo lectura a las tablas existentes.
- Login y roles básicos.
- Dashboard general.
- Listado y detalle de runs, eventos y DQ.

### Fase 2 — Detección

- Motor de reglas.
- 21 cards de categorías.
- Incidentes y reconocimiento.
- Ventanas de ejecución y umbrales.

### Fase 3 — Payloads

- Analizadores `00021`, `00022` y `00023`.
- Reglas configurables.
- Comparador JSON.
- Indicadores de inconsistencias.

### Fase 4 — Alertas e infraestructura

- Correo, Teams, Slack o webhook.
- Integración con métricas de RabbitMQ.
- Estado de servidores y aplicaciones.
- Métricas de SAP CPI.

### Fase 5 — Analítica avanzada

- Líneas base históricas.
- Detección de anomalías de volumen y duración.
- Predicción de saturación.
- Informes operativos y ejecutivos.

## 19. Resultado esperado

El producto final debe permitir responder rápidamente:

- ¿Está funcionando el bus en este momento?
- ¿Qué integración falló y desde cuándo?
- ¿En qué etapa se produjo el fallo?
- ¿Fue un problema de red, aplicación, datos, configuración o SAP?
- ¿Qué documento o persona fue afectado?
- ¿El mensaje se reintentó o duplicó?
- ¿Cuál fue el payload enviado y qué respondió SAP?
- ¿Quién reconoció o resolvió el incidente?
- ¿El problema es aislado o se está volviendo recurrente?

La interfaz debe priorizar la operación diaria: primero mostrar la salud general, luego permitir llegar desde una card o alerta hasta la ejecución, su trazabilidad, sus eventos y los payloads relacionados con el menor número posible de clics.
