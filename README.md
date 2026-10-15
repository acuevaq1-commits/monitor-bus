# Monitor de Integraciones Banner–SAP

Aplicación FastAPI para consultar `iislog.iis_run`, `iislog.iis_event`, `iislog.dq_issue` e `iisupao.plantilla_integracion` y gestionar la configuración del monitor en un esquema separado.

## Inicio

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[test]"
Copy-Item .env.example .env
# Configure MONITOR_SOURCE_DATABASE_URL, MONITOR_DATABASE_URL y las claves en .env
alembic upgrade head
uvicorn src.main:app --reload
```

Abra `http://127.0.0.1:8000`. Sin `MONITOR_SOURCE_DATABASE_URL`, las métricas indican «Sin fuente de datos». Las credenciales de administrador se configuran mediante variables de entorno. Configure un usuario de PostgreSQL con permisos `SELECT` sobre las tablas de origen. Para PostgreSQL, `MONITOR_DATABASE_URL` debe apuntar a la base donde se creará el esquema `iismonitor`; para desarrollo local puede usarse SQLite. Si una contraseña contiene `@`, `:`, `/`, `#` u otros caracteres especiales, codifíquela para URL antes de incluirla en la cadena de conexión.

Las vistas de datos abren con un rango de 7 días. El dashboard advierte por separado cuando no hubo ejecuciones en las últimas 24 horas. Las fechas visibles se muestran en `America/Lima` como `dd/mm/yyyy hh:mm:ss`; las marcas ISO originales siguen en las rutas y en las respuestas API para conservar la clave compuesta de cada ejecución.

Si el usuario PostgreSQL solo tiene permisos de lectura, configure `MONITOR_SOURCE_DATABASE_URL` con PostgreSQL y `MONITOR_DATABASE_URL=sqlite:///./monitor.db`. En ese caso, los incidentes y reglas quedan en el archivo local `monitor.db`; ejecute `alembic upgrade head` antes de iniciar la aplicación.

La aplicación lee la estructura real de las cuatro tablas de origen mediante reflexión, porque la especificación no proporciona su DDL. Algunas funciones dependen de que las columnas nombradas en la especificación existan. No ejecuta escrituras sobre esas tablas. La gestión de plantillas de producción se mantiene en modo lectura hasta definir permisos institucionales.

## Verificación

```powershell
pytest
```

## Operación

Los endpoints `/api/v1` comparten casos de uso con las vistas. Todas las búsquedas de runs requieren una ventana temporal y están paginadas. Los payloads se omiten de los listados, se limitan a 256 KiB en detalle y se enmascaran antes de responder. El motor de detección puede evaluarse bajo demanda desde `/api/v1/incidents/scan` con sesión de administrador. Configure un trabajo externo periódico para llamar ese endpoint en una instalación estable.

## Estado de implementación

Esta entrega contiene la estructura de carpetas solicitada, migración de las tablas propias, login de administrador, dashboard, consultas paginadas, detalle y trazabilidad básica, 21 categorías con estado de medición, detección inicial, reglas configurables, mantenedores del monitor, analizadores de `00021`/`00022`/`00023` y comparación estructural de JSON. La pantalla de inconsistencias consulta la cola `que.upao.iisupao.result` y compara `iis_run.status` con `summary_json.json_exec.status` y `http_status`, siempre con rango temporal y paginación. El detalle vincula el JSON enviado en `que.upao.iisupao.program.inline` mediante clave de negocio y la ejecución anterior más cercana.

Quedan pendientes de adaptar a ejemplos reales de payload: consultas generales por identificador de negocio, asignación precisa de etapas, duplicados, análisis histórico de campos distintos del estado y validaciones SAP completas. La vinculación entre envío y resultado por clave de negocio puede ser ambigua ante reintentos. La detección de ausencia usa las ventanas configuradas, pero necesita verificarse con el calendario y la carga reales. Tampoco se implementan todavía el SSO, los permisos institucionales de edición de plantillas, la entrega de alertas ni las métricas de RabbitMQ/CPI/servidores. Las categorías sin un evaluador confiable se muestran como «Sin fuente de datos».

Antes de usarlo en producción, facilite el DDL de las cuatro tablas existentes y ejemplos anonimizados de las tres integraciones. Deben probarse los índices, tiempos de respuesta y permisos con datos representativos.
