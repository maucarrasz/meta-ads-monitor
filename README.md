# meta-ads-monitor

Lee el total público de anuncios activos de un dominio en Meta Ads Library. Los errores o bloqueos nunca se convierten en cero. No usa proxies, evasión, login ni IDs de anuncios.

## Corrida diaria

`daily.yml` tiene una sola programación: `30 12 * * *` (07:30 Lima). El cron lee todas las tiendas, con 240 segundos entre dominios, en el orden regional USA/EU, LATAM, Perú y luego el orden de la hoja. La corrida es reanudable: omite antes de abrir Chrome los dominios que ya tienen una fila de hoy en Ingesta. El dispatch conserva los shards manuales y `solo_lista` para inspeccionar pendientes sin abrir el navegador. `main.py` corta las lecturas a las 12:00 Lima, también si el workflow comienza tarde. No empieza una lectura cuando quedan menos de 120 segundos.

La lista autoritativa es `Tiendas` de la Base única `1cfilechpzK22smRSAz2XatjWwkNX-y70ojc1UMifE8w`. Se resuelven las columnas por cabecera; requiere `dominio` y `decision`, acepta `SI`/`SÍ` y excluye estados que comienzan por `Descartad`. Si un dominio aparece con decisiones contradictorias queda inactivo. Las bajas no borran ni reescriben historial.

`SHEET_ID` conserva el historial legado y la lista personal `Seguimiento_Ads`: el seguimiento vigente se añade al final del robot all/0 y nunca se envía a Ingesta. Se conserva la exclusión personal previa de `info.doutornature.com`. Los demás conteos válidos se añaden a `Ingesta_Diaria` en la Base única. Un bloqueo o login detiene la corrida sin reintentos. El workflow no cancela corridas previas y conserva el grupo de concurrencia `minisniper-ads`. `spy.py`, `spy.yml` y el workflow de catálogo siguen siendo independientes; `catalogo.yml` permanece manual, sin cron propio, porque el catálogo diario se programa desde Mini Sniper.

## Worker HTTP para Mini Sniper

`ads_worker.py` expone `GET /health` sin secretos y `POST /read`. El POST admite como máximo 2048 bytes y exactamente:

```json
{"job_id":"7cce71d0-d613-4ff9-ae7a-d628edb184da","domain":"example.com"}
```

El dominio debe llegar normalizado: ASCII en minúsculas, sin esquema, ruta, puerto ni dirección IP. Se admite `www.` como parte del dominio exacto recibido y se conserva en la consulta y la evidencia; no se transforma al dominio raíz. Solo se construye una URL fija bajo `https://www.facebook.com/ads/library/` con `active_status=active`, `country=ALL`, `search_type=keyword_exact_phrase` y `q` con el dominio entre comillas. Nunca se recibe una URL de destino.

El caller y el worker comparten `MINI_SNIPER_ADS_WORKER_SECRET`. Headers:

- `X-Sniper-Timestamp`: segundos Unix, diferencia máxima de 60 segundos en cualquiera de las dos direcciones.
- `X-Sniper-Signature`: hexadecimal minúsculo de `HMAC-SHA256(secret, timestamp + "." + raw_body)`.

Se firma el cuerpo exacto enviado, no JSON serializado nuevamente. Firmas inválidas o vencidas devuelven 401 antes de abrir Chromium; un secreto sin configurar devuelve 503. Un payload inválido devuelve 400 y un cuerpo grande devuelve 413.

La lectura devuelve HTTP 200 con:

```json
{
  "status": "ready",
  "value": 42,
  "observed_at": "2026-10-15T12:30:00+00:00",
  "source": "META_AD_LIBRARY",
  "method": "meta_domain_total_v1",
  "is_estimate": true,
  "evidence_url": "https://www.facebook.com/ads/library/?...",
  "evidence_sha256": "hash SHA256 del texto real leído",
  "error_code": null
}
```

El ejemplo ilustra el contrato; no representa una observación real. En un error, `status=error` y `value=null`. El hash solo existe cuando se pudo leer texto real del body y se calcula sobre sus bytes UTF-8; no se inventa evidencia ni se deriva el hash del dominio/contador. `is_estimate` conserva el indicador `~` o `About` del total. El total no requiere cargar tarjetas ni recolectar IDs.

Cada lectura reutiliza `scraper.read_count` en un subproceso. El límite duro es 110 segundos, con eliminación de su grupo de procesos, también al interrumpir una corrida diaria. La navegación y lectura tienen además un presupuesto interno de 95 segundos. No hay reintentos ante login o bloqueo.

La corrida diaria solicita además el literal del encabezado por un canal interno del subproceso. `ads_activos_texto` conserva ese literal (`42 results`, `~1,234 results` o el mensaje real sin coincidencias), sin fabricar `~N results` ni un aproximado donde la fuente era exacta. Si falta el literal no se escribe un recibo de ingesta. Esta metadata interna no amplía el contrato HTTP. Los formatos que el importador todavía no admita se mantienen literales para que su validación los rechace de forma visible; no se convierten a otra evidencia.

## Ejecución on demand en GitHub Actions

La ruta operativa actual es `ads-demand.yml`, invocada por `workflow_dispatch` con `work_id` UUID y `domain` ASCII normalizado. El backend solicita el dispatch; el workflow no tiene cron. `demand_runner.py` reclama el trabajo con un lease UUID propio, lee solamente si ganó el claim y devuelve el resultado con ese mismo lease. Un claim duplicado no abre Chrome ni completa el trabajo ajeno.

El único secreto requerido por el workflow es `MINI_SNIPER_ADS_EXECUTOR_DATABASE_URL`: conexión privada del login `mini_sniper_ads_executor` (o su usuario de pooler con sufijo del proyecto), sin permisos SELECT sobre tablas y con EXECUTE únicamente sobre las funciones autorizadas. Se conecta por TLS, con timeout de conexión de 10 segundos y de sentencia de 10 segundos. Reclamar y completar son transacciones cortas separadas; no se mantiene una conexión abierta durante la lectura del navegador. Una DSN de administración se rechaza antes del callback. Netlify nunca recibe esta credencial.

El runner conserva un transporte REST opcional para infraestructura futura: `SUPABASE_URL` y `MINI_SNIPER_ADS_RPC_TOKEN`. Una clave dedicada `sb_secret_` se envía únicamente como `apikey`, sin Bearer; un JWT legado del rol executor requiere además `SUPABASE_ANON_KEY` y se envía como Bearer. El workflow operativo no requiere ni inyecta estas variables. La DSN privada tiene preferencia si está configurada. No se ha habilitado un plan Pro para obtener claves personalizadas.

Solo llama `ads_demand_claim(p_work_id,p_domain,p_lease)` y `ads_demand_complete(p_work_id,p_lease,p_result)`. Se validan UUID, dominio, origen HTTPS de Supabase, respuesta HTTP, tamaño de respuesta y confirmación booleana del callback. No se registran tokens ni cuerpos de respuesta; los redirects están prohibidos. Los errores del lector completan el trabajo con `value=null`. Un mensaje de consulta sin coincidencias no se promueve a cero verificado: requiere un encabezado real `0 results` para entregar `ready` con valor cero.

El job tiene timeout de cinco minutos. Instala el lector `playwright==1.64.0` y el callback `psycopg[binary]==3.2.13` desde `requirements-worker.lock` con hashes y caché pip. Usa `PLAYWRIGHT_CHROMIUM_CHANNEL=chrome` para el Chrome preinstalado del runner Ubuntu. No descarga Chromium, instala apt, usa OIDC ni instala dependencias de Sheets. El canal es opcional: sin esa variable, los lectores existentes mantienen su selección de navegador. Referencias: [navegadores de Playwright](https://playwright.dev/python/docs/browsers) e [imagen Ubuntu de GitHub](https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md).

## Preparación de Cloud Run (pendiente, sin habilitar gasto)

El Dockerfile instala Chromium y sus dependencias en la imagen, y ejecuta el worker con usuario sin privilegios. `deploy-worker.yml` solamente responde a `workflow_dispatch`: no se despliega por push ni por cron. No activa APIs, crea cuentas, otorga IAM ni crea infraestructura automáticamente.

Los créditos de Google no están activos según lo indicado por el propietario. Cloud Run queda pendiente; el Dockerfile y el workflow permanecen preparados y no se ha desplegado el servicio. El despliegue queda deshabilitado hasta verificar créditos y presupuesto del proyecto `mauricio-ai-hub`. Después de esa verificación, se deben configurar estas variables de GitHub:

- `MINI_SNIPER_GCP_CREDITS_VERIFIED=true`, solo tras la verificación real.
- `MINI_SNIPER_ADS_ARTIFACT_REPOSITORY`: repositorio Docker ya existente en Artifact Registry.
- `MINI_SNIPER_ADS_RUNTIME_SERVICE_ACCOUNT`: cuenta runtime dedicada, con acceso de lectura únicamente al secreto HMAC necesario.
- `MINI_SNIPER_ADS_HMAC_SECRET_NAME`: nombre del secreto ya creado en Secret Manager. Su valor debe coincidir con el secreto del caller Netlify; no poner su valor en GitHub Variables ni en el código.
- `MINI_SNIPER_ADS_REGION`: región de los recursos existentes (por defecto `us-central1`).

El dispatch requiere además marcar `credits_verified`. Ambos controles se comprueban antes de OIDC, construir o desplegar. El proveedor OIDC existente es `projects/277394231713/locations/global/workloadIdentityPools/github-meta-ads/providers/github-actions`, con la cuenta de despliegue existente `meta-ads-robot@mauricio-ai-hub.iam.gserviceaccount.com`. Sus permisos efectivos para Artifact Registry, Cloud Run e impersonar el runtime deben revisarse antes de habilitar el despliegue; el workflow no los amplía.

La configuración de despliegue fija CPU 1, RAM 1 GiB, concurrencia 1, mínimo 0 y máximo 1 tanto de servicio como de revisión, timeout 120 segundos, CPU limitada a solicitudes y sin startup CPU boost. El endpoint permite invocaciones HTTP públicas para el caller Netlify y exige HMAC en `/read`. Referencia de flags: [gcloud run deploy](https://docs.cloud.google.com/sdk/gcloud/reference/run/deploy).

## Verificación local

```sh
python -m pip install -r requirements.txt pytest
python -m pip install --require-hashes -r requirements-worker.lock
python -m pytest -q
docker build -t mini-sniper-meta-worker .
docker run --rm -p 8080:8080 --env MINI_SNIPER_ADS_WORKER_SECRET mini-sniper-meta-worker
```

Las pruebas usan solicitudes HTTP reales contra localhost y procesos reales para verificar el timeout. Las páginas de prueba reemplazan únicamente la dependencia de navegador; no se hacen consultas reales a Meta ni a Sheets. Nunca subir `.env`, credenciales OIDC, estados de sesión o secretos.
