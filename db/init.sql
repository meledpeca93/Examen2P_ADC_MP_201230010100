
IF DB_ID(N'OrdenesDB') IS NULL
BEGIN
    CREATE DATABASE [OrdenesDB];
END;
GO

USE [OrdenesDB];
GO

IF OBJECT_ID(N'dbo.ordenes', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ordenes (
        id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        cliente NVARCHAR(120) NOT NULL,
        fecha DATETIME2 NOT NULL,
        estado NVARCHAR(20) NOT NULL,
        total DECIMAL(12,2) NOT NULL
            CONSTRAINT DF_ordenes_total DEFAULT (0)
    );
END;
GO

IF OBJECT_ID(N'dbo.orden_detalle', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.orden_detalle (
        id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        orden_id INT NOT NULL,
        producto NVARCHAR(150) NOT NULL,
        cantidad INT NOT NULL CHECK (cantidad > 0),
        precio_unitario DECIMAL(12,2) NOT NULL CHECK (precio_unitario >= 0),
        subtotal DECIMAL(12,2) NOT NULL,
        CONSTRAINT FK_orden_detalle_ordenes
            FOREIGN KEY (orden_id)
            REFERENCES dbo.ordenes(id)
            ON DELETE CASCADE
    );
END;
GO

IF NOT EXISTS (SELECT 1 FROM dbo.ordenes)
BEGIN
    SET IDENTITY_INSERT dbo.ordenes ON;

    INSERT INTO dbo.ordenes (id, cliente, fecha, estado, total)
    VALUES
        (1, N'Cliente Demo Norte',  '2026-10-01T10:00:00', N'Pendiente', 250.00),
        (2, N'Cliente Demo Centro', '2026-10-02T11:30:00', N'Pagada',    450.00),
        (3, N'Cliente Demo Sur',    '2026-10-03T09:15:00', N'Anulada',   160.00),
        (4, N'Cliente Demo Este',   '2026-10-04T14:00:00', N'Pendiente', 820.00),
        (5, N'Cliente Demo Oeste',  '2026-10-05T16:45:00', N'Pagada',    365.00);

    SET IDENTITY_INSERT dbo.ordenes OFF;

    INSERT INTO dbo.orden_detalle
        (orden_id, producto, cantidad, precio_unitario, subtotal)
    VALUES
        (1, N'Teclado',        2,  50.00, 100.00),
        (1, N'Mouse',          3,  50.00, 150.00),
        (2, N'Monitor',        1, 300.00, 300.00),
        (2, N'Cable HDMI',     3,  50.00, 150.00),
        (3, N'Soporte laptop', 2,  40.00,  80.00),
        (3, N'Webcam',         1,  80.00,  80.00),
        (4, N'Lámpara',        4,  80.00, 320.00),
        (4, N'Silla',          2, 250.00, 500.00),
        (5, N'Memoria USB',    5,  25.00, 125.00),
        (5, N'Audífonos',      2, 120.00, 240.00);
END;
GO