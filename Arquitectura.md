# Arquitectura — Examen del Segundo Parcial

## 1. Base de datos (db)

### 1.1 Imagen oficial y credenciales

- Imagen: `mcr.microsoft.com/mssql/server:2022-latest`.
- SQL Server aceptará la licencia mediante `ACCEPT_EULA=Y`.
- La contraseña de `sa` se proporcionará mediante `MSSQL_SA_PASSWORD` desde el archivo local `.env`; no se escribirá como valor real en `compose.yaml`.
- La contraseña de la cuenta de aplicación se proporcionará mediante `MSSQL_APP_PASSWORD`, también solo en `.env`.
- `.env` no se publicará en GitHub. `.env.example` contendrá únicamente un valor ficticio.
- La contraseña real se elegirá y guardará localmente; no se compartirá en el chat.
- El Mac anfitrión es `arm64`; SQL Server se ejecuta como imagen `linux/amd64` mediante emulación. La prueba local logró iniciar el motor y dejarlo `healthy`, pero Microsoft indica que esta emulación no está soportada. Para un entorno oficialmente compatible, se usará un host Docker `x86_64`.

### 1.2 Volumen persistente

- Se usará el volumen nombrado `ventasadc_sqlserver2022_data`, montado en `/var/opt/mssql`.
- `docker compose down` conservará los datos. `docker compose down -v` eliminará el volumen y sus datos.

### 1.3 Esquema de las tablas

- `ordenes`:
  - `id INT IDENTITY PRIMARY KEY`
  - `cliente NVARCHAR(120) NOT NULL`
  - `fecha DATETIME2 NOT NULL`
  - `estado NVARCHAR(20) NOT NULL`
  - `total DECIMAL(12,2) NOT NULL DEFAULT 0`
- `orden_detalle`:
  - `id INT IDENTITY PRIMARY KEY`
  - `orden_id INT NOT NULL` con clave foránea a `ordenes(id)` y borrado en cascada
  - `producto NVARCHAR(150) NOT NULL`
  - `cantidad INT NOT NULL CHECK (cantidad > 0)`
  - `precio_unitario DECIMAL(12,2) NOT NULL CHECK (precio_unitario >= 0)`
  - `subtotal DECIMAL(12,2) NOT NULL`
- La API calculará el subtotal y recalculará `ordenes.total` al agregar, modificar o eliminar detalles; el cliente no podrá establecer directamente el total.

### 1.4 Datos de prueba

- `init.sql` incluirá al menos cinco órdenes con clientes y productos ficticios, cada una con dos o más líneas de detalle.
- Los datos cubrirán estados variados (`Pendiente`, `Pagada`, `Anulada`) y tendrán subtotales y totales consistentes.
- La inicialización insertará las órdenes de prueba solo si la tabla `ordenes` está vacía, para evitar duplicados al reiniciar la API.

### 1.5 Ejecución de `init.sql`

- El servicio `api` ejecutará `init.sql` después de que SQL Server esté sano.
- El script usará `GO` como separador de lotes; la API dividirá el archivo por esos separadores y ejecutará cada lote por separado con autocommit habilitado.
- La API usará `sa` únicamente para inicializar `OrdenesDB` y crear o actualizar el login `ventasadc_app` usando `MSSQL_APP_PASSWORD`.
- `ventasadc_app` recibirá permisos de lectura y escritura en `OrdenesDB`.
- Para las operaciones normales, la API usará `ventasadc_app`, no `sa`.
- Si falla la inicialización, la API registrará el error y no iniciará como si estuviera lista.
- El procedimiento también se documentará en `README.md`.

### 1.6 Healthcheck

- El servicio `db` ejecutará `/opt/mssql-tools18/bin/sqlcmd` contra `localhost` con la cuenta `sa` y ejecutará `SELECT 1`.
- El healthcheck verificará una consulta real al motor; `api` esperará a que `db` tenga estado `healthy`.
- Referencia: [Microsoft Learn — Deploy and Connect to SQL Server Linux Containers](https://learn.microsoft.com/en-us/sql/linux/containers/deploy?view=sql-server-ver17).

### 1.7 Acceso desde el host

- SQL Server escuchará en el puerto `1433` dentro de Docker.
- Se publicará `127.0.0.1:14330` del Mac hacia `1433` del contenedor para conectarse desde DBeaver, sin exponer SQL Server a otros equipos de la red.
- Los servicios de Docker se conectarán por la red interna; la API usará `db:1433`.

### 1.8 Dependencias Python para conectar la API

- La API utilizará `Flask==3.1.1` y `pyodbc==5.2.0`, declarados en `api/requirements.txt`.
- La imagen de la API usará `python:3.12-slim-bookworm` e instalará Microsoft ODBC Driver 18 siguiendo las instrucciones oficiales para Debian 12.
- El contexto de construcción de la imagen será la raíz del repositorio para incluir `db/init.sql` en `/app/db/init.sql`.
- Un `.dockerignore` en la raíz excluirá `.env` y otros archivos locales del contexto de construcción, sin excluir `api/` ni `db/`.
- El Dockerfile copiará e instalará `requirements.txt` antes de copiar el código de la aplicación para aprovechar la caché de capas.
- La API se ejecutará con un usuario sin privilegios; el comando de inicio será `python app.py`, que inicializará la base antes de servir solicitudes.

### 1.9 Validación local

- `docker compose config --quiet` terminó correctamente.
- La imagen de la API se construyó correctamente con `docker compose build api`.
- `db` y `api` aparecen `healthy` en `docker compose ps`.
- La persistencia se comprobó tras `docker compose down` y `docker compose up -d db`, sin eliminar el volumen.
- Desde el contenedor `api`, una consulta con `ventasadc_app` devolvió 5 órdenes y 10 detalles.
- La documentación de la ejecución de `init.sql` en `README.md` queda pendiente.

## 2. API REST

### 2.1 Listar órdenes

- `GET /api/ordenes` devuelve las órdenes en JSON con HTTP `200`.
- La API consulta SQL Server como `ventasadc_app` a través de `db:1433`.
- Validación local: respuesta HTTP `200` con las 5 órdenes de prueba.

### 2.2 Consultar una orden con sus detalles

- `GET /api/ordenes/<id>` devuelve la orden y sus líneas de detalle en JSON con HTTP `200`.
- Si el ID no corresponde a una orden, devuelve HTTP `404` con un error JSON.
- La consulta usa un `LEFT JOIN` para representar una orden sin líneas con una lista `detalles` vacía.
- Validación local: `/api/ordenes/1` devolvió HTTP `200` con dos detalles; `/api/ordenes/999` devolvió HTTP `404` con `{"error":"No existe la orden 999"}`.

### 2.3 Crear una orden

- `POST /api/ordenes` aceptará exactamente `cliente`, `fecha` y `estado` en JSON.
- `cliente` debe ser no vacío y tener como máximo 120 caracteres; `fecha` debe ser ISO 8601; `estado` debe ser `Pendiente`, `Pagada` o `Anulada`.
- El cliente no enviará `total`; la base lo inicializará en cero.
- Datos faltantes o inválidos, JSON incorrecto o campos adicionales (incluido `total`) devolverán HTTP `400` en JSON.
- Una creación correcta devolverá HTTP `201` en JSON con el ID, datos de la orden y total inicial.
- Validación local: se creó `Cliente Prueba API` con HTTP `201`, ID `1001` y total `0.0`; los valores `IDENTITY` pueden tener saltos y no deben suponerse consecutivos.
- Enviar el campo no permitido `total` devolvió HTTP `400` en JSON. La lista quedó en seis órdenes (`1, 2, 3, 4, 5, 1001`), confirmando que el POST inválido no insertó otra fila.
- Validación de rechazo: enviar el campo no permitido `total` devolvió HTTP `400` y JSON; la lista siguió teniendo seis órdenes (`1, 2, 3, 4, 5, 1001`), por lo que la solicitud inválida no insertó otra fila.

### 2.4 Actualizar una orden

- `PUT /api/ordenes/<id>` recibirá el objeto completo con exactamente `cliente`, `fecha` y `estado`, usando las mismas validaciones de `POST /api/ordenes`.
- No se permite modificar `total` directamente; el total y los detalles existentes se conservan.
- Una actualización correcta devolverá HTTP `200` con los datos de la orden actualizada.
- Un JSON inválido, campos faltantes o adicionales, o valores inválidos devolverán HTTP `400` en JSON.
- Si el ID no corresponde a una orden, devolverá HTTP `404` en JSON.
- Validación con Docker Compose: actualizar la orden `1001` devolvió HTTP `200`, con cliente `Cliente Prueba API Actualizado`, estado `Pagada` y total `0.0`.
- Enviar `total` en el cuerpo devolvió HTTP `400` con `{"error":"Campos no permitidos: total"}`.
- Actualizar el ID `999` devolvió HTTP `404` con `{"error":"No existe la orden 999"}`.
- Un GET posterior de la orden `1001` devolvió HTTP `200` y confirmó que conserva el cliente actualizado, estado `Pagada`, total `0.0` y detalles vacíos; la solicitud inválida no la modificó.

### 2.5 Eliminar una orden

- `DELETE /api/ordenes/<id>` eliminará la orden y sus detalles relacionados mediante la clave foránea con `ON DELETE CASCADE`.
- Si se elimina una orden existente, responderá HTTP `204 No Content`; si no existe, responderá HTTP `404` en JSON.
- Validación con Docker Compose: DELETE del ID `999` devolvió HTTP `404` con `{"error":"No existe la orden 999"}`.
- DELETE de la orden de prueba `1001` devolvió HTTP `204 No Content`; GET posterior de ese ID devolvió HTTP `404`, confirmando que fue eliminada.
- La orden `1001` no tenía detalles; la eliminación en cascada está declarada en la FK, pero no se verificó en ejecución con una orden que tuviera detalles.

### 2.6 Agregar un detalle a una orden

- `POST /api/ordenes/<id>/detalles` aceptará exactamente `producto`, `cantidad` y `precio_unitario`.
- `producto` debe ser texto no vacío de hasta 150 caracteres; `cantidad` un entero positivo; `precio_unitario` un valor no negativo con hasta dos decimales.
- La API calculará el subtotal y recalculará el total de la orden dentro de una transacción. No se aceptan `subtotal` ni `total` en la solicitud.
- Una creación correcta devolverá HTTP `201` con los datos del detalle, subtotal y total actualizado de la orden.
- Los datos inválidos devolverán HTTP `400`; si la orden no existe, devolverá HTTP `404`.
- Validación con Docker Compose: se crearon dos detalles para la orden temporal `1002`; el primero devolvió HTTP `201` con subtotal y total `100.0`; el segundo devolvió HTTP `201` con subtotal `150.0` y total acumulado `250.0`.
- GET de la orden `1002` confirmó los dos detalles y total `250.0`.
- Enviar `subtotal` y `total` devolvió HTTP `400` con `{"error":"Campos no permitidos: subtotal, total"}`; el GET posterior confirmó que la orden siguió con dos detalles y total `250.0`.
- Intentar agregar un detalle a la orden `999` devolvió HTTP `404` con `{"error":"No existe la orden 999"}`.

### 2.7 Listar los detalles de una orden

- `GET /api/ordenes/<id>/detalles` devuelve una lista JSON con las líneas de detalle de la orden.
- Si la orden existe sin detalles, devuelve HTTP `200` con una lista vacía; si no existe, devuelve HTTP `404` en JSON.
- Validación con Docker Compose: GET de la orden `1002` devolvió HTTP `200` con sus dos detalles; GET de la orden `999` devolvió HTTP `404` con `{"error":"No existe la orden 999"}`.

### 2.8 Actualizar un detalle

- `PUT /api/detalles/<id>` aceptará exactamente `producto`, `cantidad` y `precio_unitario`.
- La API validará esos campos, calculará el subtotal y recalculará el total de la orden dentro de una transacción. No se aceptan `subtotal` ni `total`.
- Una actualización correcta devolverá HTTP `200`; los datos inválidos devolverán HTTP `400`; si el detalle no existe, devolverá HTTP `404`.
- Validación con Docker Compose: actualizar el detalle `1002` devolvió HTTP `200`, con subtotal `240.0` y total de orden `390.0`.
- Enviar `subtotal` y `total` devolvió HTTP `400`; actualizar el ID `999` devolvió HTTP `404` con `{"error":"No existe el detalle 999"}`.
- GET posterior de la orden `1002` confirmó los subtotales `240.0` y `150.0`, y total `390.0`; la solicitud inválida no modificó los datos.

### 2.9 Eliminar un detalle

- `DELETE /api/detalles/<id>` eliminará una línea y recalculará el total de su orden dentro de una transacción.
- Una eliminación correcta devolverá HTTP `204 No Content`; si el detalle no existe, devolverá HTTP `404` en JSON.
- Validación con Docker Compose: eliminar el detalle `1003` devolvió HTTP `204`; GET posterior de la orden `1002` confirmó que quedó solo el detalle `1002` y que el total se recalculó de `390.0` a `240.0`.
- DELETE del ID `999` devolvió HTTP `404` con `{"error":"No existe el detalle 999"}`.

### 2.10 Estado de la API

- `GET /health` devuelve `{"status":"healthy"}` con HTTP `200` y se usa en el healthcheck del contenedor `api`.
