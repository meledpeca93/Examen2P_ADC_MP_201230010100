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
