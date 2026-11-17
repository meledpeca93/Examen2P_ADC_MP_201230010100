import logging
import os
from contextlib import closing
from datetime import datetime, timezone

import pyodbc
from flask import Flask, jsonify, request
from decimal import Decimal, InvalidOperation
from init_db import _connection_string, initialize_database


app = Flask(__name__)

ORDER_FIELDS = frozenset({"cliente", "fecha", "estado"})
ORDER_STATES = frozenset({"Pendiente", "Pagada", "Anulada"})
DETAIL_FIELDS = frozenset({"producto", "cantidad", "precio_unitario"})


def _bad_detail_request(message):
    logging.warning("Solicitud de detalle inválida: %s", message)
    return jsonify({"error": message}), 400


def _validate_detail_data(data):
    if not isinstance(data, dict):
        return "El cuerpo debe ser un objeto JSON."

    missing = DETAIL_FIELDS - set(data)
    extra = set(data) - DETAIL_FIELDS
    errors = []

    if missing:
        errors.append(f"Faltan campos: {', '.join(sorted(missing))}")
    if extra:
        errors.append(f"Campos no permitidos: {', '.join(sorted(extra))}")
    if errors:
        return "; ".join(errors)

    producto = data["producto"]
    if not isinstance(producto, str) or not producto.strip():
        return "producto debe ser texto no vacío."
    producto = producto.strip()
    if len(producto) > 150:
        return "producto no puede exceder 150 caracteres."

    cantidad = data["cantidad"]
    if isinstance(cantidad, bool) or not isinstance(cantidad, int):
        return "cantidad debe ser un número entero positivo."
    if cantidad < 1 or cantidad > 2147483647:
        return "cantidad debe estar entre 1 y 2147483647."

    precio_value = data["precio_unitario"]
    if isinstance(precio_value, bool) or not isinstance(precio_value, (int, float)):
        return "precio_unitario debe ser un número no negativo."
    try:
        precio_unitario = Decimal(str(precio_value))
    except (InvalidOperation, ValueError):
        return "precio_unitario debe ser un número no negativo."

    max_decimal = Decimal("9999999999.99")
    if (
        not precio_unitario.is_finite()
        or precio_unitario < 0
        or precio_unitario > max_decimal
        or precio_unitario.as_tuple().exponent < -2
    ):
        return "precio_unitario debe ser no negativo y tener como máximo dos decimales."

    subtotal = precio_unitario * cantidad
    if subtotal > max_decimal:
        return "El subtotal excede el máximo permitido."

    return producto, cantidad, precio_unitario, subtotal


def _bad_order_request(message):
    logging.warning("Solicitud de orden inválida: %s", message)
    return jsonify({"error": message}), 400


def _validate_order_data(data):
    if not isinstance(data, dict):
        return "El cuerpo debe ser un objeto JSON."

    missing = ORDER_FIELDS - set(data)
    extra = set(data) - ORDER_FIELDS
    errors = []

    if missing:
        errors.append(f"Faltan campos: {', '.join(sorted(missing))}")
    if extra:
        errors.append(f"Campos no permitidos: {', '.join(sorted(extra))}")
    if errors:
        return "; ".join(errors)

    cliente = data["cliente"]
    if not isinstance(cliente, str) or not cliente.strip():
        return "cliente debe ser texto no vacío."
    cliente = cliente.strip()
    if len(cliente) > 120:
        return "cliente no puede exceder 120 caracteres."

    fecha_value = data["fecha"]
    if not isinstance(fecha_value, str):
        return "fecha debe ser una fecha ISO 8601."

    try:
        fecha = datetime.fromisoformat(fecha_value.replace("Z", "+00:00"))
    except ValueError:
        return "fecha debe ser una fecha ISO 8601."

    if fecha.tzinfo is not None:
        fecha = fecha.astimezone(timezone.utc).replace(tzinfo=None)

    estado = data["estado"]
    if not isinstance(estado, str) or estado.strip() not in ORDER_STATES:
        return "estado debe ser Pendiente, Pagada o Anulada."

    return cliente, fecha, estado.strip()


def _get_database_connection():
    connection_string = _connection_string(
        "OrdenesDB",
        "ventasadc_app",
        os.environ["MSSQL_APP_PASSWORD"],
    )
    return pyodbc.connect(connection_string, autocommit=True)


@app.errorhandler(404)
def not_found(_error):
    return jsonify({"error": "Recurso no encontrado"}), 404


@app.get("/health")
def health():
    return jsonify({"status": "healthy"}), 200

#LISTAR ORDENES DE VENTA
@app.get("/api/ordenes")
def list_orders():
    try:
        with closing(_get_database_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT id, cliente, fecha, estado, total
                FROM dbo.ordenes
                ORDER BY id
                """
            )
            orders = [
                {
                    "id": row.id,
                    "cliente": row.cliente,
                    "fecha": row.fecha.isoformat(),
                    "estado": row.estado,
                    "total": float(row.total),
                }
                for row in cursor.fetchall()
            ]

        return jsonify(orders), 200
    except pyodbc.Error:
        logging.exception("Error al consultar la lista de órdenes")
        return jsonify({"error": "No se pudieron consultar las órdenes"}), 500


    

#LISTAR UNA ORDEN SEGUN SU ID CON TODOS SU DETALLES
@app.get("/api/ordenes/<int:order_id>")
def get_order(order_id):
    try:
        with closing(_get_database_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    o.id AS orden_id,
                    o.cliente,
                    o.fecha,
                    o.estado,
                    o.total,
                    d.id AS detalle_id,
                    d.producto,
                    d.cantidad,
                    d.precio_unitario,
                    d.subtotal
                FROM dbo.ordenes AS o
                LEFT JOIN dbo.orden_detalle AS d
                    ON d.orden_id = o.id
                WHERE o.id = ?
                ORDER BY d.id
                """,
                order_id,
            )
            rows = cursor.fetchall()

        if not rows:
            return jsonify({"error": f"No existe la orden {order_id}"}), 404

        first_row = rows[0]
        order = {
            "id": first_row.orden_id,
            "cliente": first_row.cliente,
            "fecha": first_row.fecha.isoformat(),
            "estado": first_row.estado,
            "total": float(first_row.total),
            "detalles": [],
        }

        for row in rows:
            if row.detalle_id is not None:
                order["detalles"].append(
                    {
                        "id": row.detalle_id,
                        "orden_id": first_row.orden_id,
                        "producto": row.producto,
                        "cantidad": row.cantidad,
                        "precio_unitario": float(row.precio_unitario),
                        "subtotal": float(row.subtotal),
                    }
                )

        return jsonify(order), 200
    except pyodbc.Error:
        logging.exception("Error al consultar la orden %s", order_id)
        return jsonify({"error": "No se pudo consultar la orden"}), 500



    
#POST PARA CREAR UNA NUEVA ORDEN DE VENTA
@app.post("/api/ordenes")
def create_order():
    validated = _validate_order_data(request.get_json(silent=True))
    if isinstance(validated, str):
        return _bad_order_request(validated)
    cliente, fecha, estado = validated

    try:
        with closing(_get_database_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT INTO dbo.ordenes (cliente, fecha, estado)
                OUTPUT INSERTED.id AS id, INSERTED.total AS total
                VALUES (?, ?, ?)
                """,
                cliente,
                fecha,
                estado,
            )
            created = cursor.fetchone()

        if created is None:
            logging.error("La inserción no devolvió el ID de la orden creada.")
            return jsonify({"error": "No se pudo confirmar la creación."}), 500

        return (
            jsonify(
                {
                    "id": created.id,
                    "cliente": cliente,
                    "fecha": fecha.isoformat(),
                    "estado": estado,
                    "total": float(created.total),
                }
            ),
            201,
        )
    except pyodbc.Error:
        logging.exception("Error al crear una orden")
        return jsonify({"error": "No se pudo crear la orden"}), 500




#PUT PARA ACTUALIZAR LOS DATOS DE UNA ORDEN
@app.put("/api/ordenes/<int:order_id>")
def update_order(order_id):
    validated = _validate_order_data(request.get_json(silent=True))
    if isinstance(validated, str):
        return _bad_order_request(validated)
    cliente, fecha, estado = validated

    try:
        with closing(_get_database_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                UPDATE dbo.ordenes
                SET cliente = ?, fecha = ?, estado = ?
                OUTPUT
                    INSERTED.id AS id,
                    INSERTED.cliente AS cliente,
                    INSERTED.fecha AS fecha,
                    INSERTED.estado AS estado,
                    INSERTED.total AS total
                WHERE id = ?
                """,
                cliente,
                fecha,
                estado,
                order_id,
            )
            updated = cursor.fetchone()

        if updated is None:
            return jsonify({"error": f"No existe la orden {order_id}"}), 404

        return (
            jsonify(
                {
                    "id": updated.id,
                    "cliente": updated.cliente,
                    "fecha": updated.fecha.isoformat(),
                    "estado": updated.estado,
                    "total": float(updated.total),
                }
            ),
            200,
        )
    except pyodbc.Error:
        logging.exception("Error al actualizar la orden %s", order_id)
        return jsonify({"error": "No se pudo actualizar la orden"}), 500




    #DELETE PARA ELIMINAR UNA ORDEN DE VENTA
@app.delete("/api/ordenes/<int:order_id>")
def delete_order(order_id):
    try:
        with closing(_get_database_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                DELETE FROM dbo.ordenes
                OUTPUT DELETED.id AS id
                WHERE id = ?
                """,
                order_id,
            )
            deleted = cursor.fetchone()

        if deleted is None:
            return jsonify({"error": f"No existe la orden {order_id}"}), 404

        return "", 204
    except pyodbc.Error:
        logging.exception("Error al eliminar la orden %s", order_id)
        return jsonify({"error": "No se pudo eliminar la orden"}), 500



#DETALLES DE LA ORDEN DE VENTA
@app.post("/api/ordenes/<int:order_id>/detalles")
def add_order_detail(order_id):
    validated = _validate_detail_data(request.get_json(silent=True))
    if isinstance(validated, str):
        return _bad_detail_request(validated)
    producto, cantidad, precio_unitario, subtotal = validated

    try:
        with closing(_get_database_connection()) as connection:
            connection.autocommit = False
            cursor = connection.cursor()
            cursor.execute(
                "SELECT id FROM dbo.ordenes WITH (UPDLOCK, HOLDLOCK) WHERE id = ?",
                order_id,
            )
            if cursor.fetchone() is None:
                return jsonify({"error": f"No existe la orden {order_id}"}), 404

            cursor.execute(
                """
                INSERT INTO dbo.orden_detalle
                    (orden_id, producto, cantidad, precio_unitario, subtotal)
                OUTPUT INSERTED.id AS id
                VALUES (?, ?, ?, ?, ?)
                """,
                order_id,
                producto,
                cantidad,
                precio_unitario,
                subtotal,
            )
            created = cursor.fetchone()
            if created is None:
                logging.error("La inserción no devolvió el ID del detalle creado.")
                return jsonify({"error": "No se pudo confirmar la creación."}), 500

            cursor.execute(
                """
                UPDATE dbo.ordenes
                SET total = (
                    SELECT COALESCE(SUM(subtotal), 0)
                    FROM dbo.orden_detalle
                    WHERE orden_id = ?
                )
                OUTPUT INSERTED.total AS total
                WHERE id = ?
                """,
                order_id,
                order_id,
            )
            updated_order = cursor.fetchone()
            if updated_order is None:
                logging.error("No se pudo recuperar el total actualizado de la orden.")
                return jsonify(
                    {"error": "No se pudo confirmar el total de la orden."}
                ), 500

            connection.commit()

        return (
            jsonify(
                {
                    "id": created.id,
                    "orden_id": order_id,
                    "producto": producto,
                    "cantidad": cantidad,
                    "precio_unitario": float(precio_unitario),
                    "subtotal": float(subtotal),
                    "total_orden": float(updated_order.total),
                }
            ),
            201,
        )
    except pyodbc.Error:
        logging.exception("Error al crear un detalle para la orden %s", order_id)
        return jsonify({"error": "No se pudo crear el detalle de la orden"}), 500


    

#GET /api/ordenes/<id>/detalles. GET DE DETALLES
@app.get("/api/ordenes/<int:order_id>/detalles")
def list_order_details(order_id):
    try:
        with closing(_get_database_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    o.id AS orden_id,
                    d.id AS detalle_id,
                    d.producto,
                    d.cantidad,
                    d.precio_unitario,
                    d.subtotal
                FROM dbo.ordenes AS o
                LEFT JOIN dbo.orden_detalle AS d
                    ON d.orden_id = o.id
                WHERE o.id = ?
                ORDER BY d.id
                """,
                order_id,
            )
            rows = cursor.fetchall()

        if not rows:
            return jsonify({"error": f"No existe la orden {order_id}"}), 404

        details = [
            {
                "id": row.detalle_id,
                "orden_id": row.orden_id,
                "producto": row.producto,
                "cantidad": row.cantidad,
                "precio_unitario": float(row.precio_unitario),
                "subtotal": float(row.subtotal),
            }
            for row in rows
            if row.detalle_id is not None
        ]
        return jsonify(details), 200
    except pyodbc.Error:
        logging.exception("Error al consultar los detalles de la orden %s", order_id)
        return jsonify({"error": "No se pudieron consultar los detalles de la orden"}), 500



#DETALLES DE LA ORDEN DE VENTA
@app.put("/api/detalles/<int:detail_id>")
def update_order_detail(detail_id):
    validated = _validate_detail_data(request.get_json(silent=True))
    if isinstance(validated, str):
        return _bad_detail_request(validated)
    producto, cantidad, precio_unitario, subtotal = validated

    try:
        with closing(_get_database_connection()) as connection:
            connection.autocommit = False
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT orden_id
                FROM dbo.orden_detalle WITH (UPDLOCK, HOLDLOCK)
                WHERE id = ?
                """,
                detail_id,
            )
            detail_order = cursor.fetchone()
            if detail_order is None:
                return jsonify({"error": f"No existe el detalle {detail_id}"}), 404

            order_id = detail_order.orden_id
            cursor.execute(
                """
                UPDATE dbo.orden_detalle
                SET producto = ?, cantidad = ?, precio_unitario = ?, subtotal = ?
                OUTPUT
                    INSERTED.id AS id,
                    INSERTED.orden_id AS orden_id,
                    INSERTED.producto AS producto,
                    INSERTED.cantidad AS cantidad,
                    INSERTED.precio_unitario AS precio_unitario,
                    INSERTED.subtotal AS subtotal
                WHERE id = ?
                """,
                producto,
                cantidad,
                precio_unitario,
                subtotal,
                detail_id,
            )
            updated = cursor.fetchone()
            if updated is None:
                logging.error("No se pudo recuperar el detalle actualizado %s", detail_id)
                return jsonify({"error": "No se pudo confirmar la actualización."}), 500

            cursor.execute(
                """
                UPDATE dbo.ordenes
                SET total = (
                    SELECT COALESCE(SUM(subtotal), 0)
                    FROM dbo.orden_detalle
                    WHERE orden_id = ?
                )
                OUTPUT INSERTED.total AS total
                WHERE id = ?
                """,
                order_id,
                order_id,
            )
            updated_order = cursor.fetchone()
            if updated_order is None:
                logging.error(
                    "No se pudo recuperar el total actualizado de la orden %s",
                    order_id,
                )
                return jsonify({"error": "No se pudo confirmar el total de la orden."}), 500

            connection.commit()

        return (
            jsonify(
                {
                    "id": updated.id,
                    "orden_id": updated.orden_id,
                    "producto": updated.producto,
                    "cantidad": updated.cantidad,
                    "precio_unitario": float(updated.precio_unitario),
                    "subtotal": float(updated.subtotal),
                    "total_orden": float(updated_order.total),
                }
            ),
            200,
        )
    except pyodbc.Error:
        logging.exception("Error al actualizar el detalle %s", detail_id)
        return jsonify({"error": "No se pudo actualizar el detalle"}), 500


#DELETE PARA ELIMINAR UN DETALLE DE LA ORDEN DE VENTA
@app.delete("/api/detalles/<int:detail_id>")
def delete_order_detail(detail_id):
    try:
        with closing(_get_database_connection()) as connection:
            connection.autocommit = False
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT orden_id
                FROM dbo.orden_detalle WITH (UPDLOCK, HOLDLOCK)
                WHERE id = ?
                """,
                detail_id,
            )
            detail_order = cursor.fetchone()
            if detail_order is None:
                return jsonify({"error": f"No existe el detalle {detail_id}"}), 404

            order_id = detail_order.orden_id
            cursor.execute(
                """
                DELETE FROM dbo.orden_detalle
                OUTPUT DELETED.id AS id
                WHERE id = ?
                """,
                detail_id,
            )
            deleted = cursor.fetchone()
            if deleted is None:
                logging.error("No se pudo recuperar el detalle eliminado %s", detail_id)
                return jsonify({"error": "No se pudo confirmar la eliminación."}), 500

            cursor.execute(
                """
                UPDATE dbo.ordenes
                SET total = (
                    SELECT COALESCE(SUM(subtotal), 0)
                    FROM dbo.orden_detalle
                    WHERE orden_id = ?
                )
                OUTPUT INSERTED.total AS total
                WHERE id = ?
                """,
                order_id,
                order_id,
            )
            updated_order = cursor.fetchone()
            if updated_order is None:
                logging.error(
                    "No se pudo recuperar el total actualizado de la orden %s",
                    order_id,
                )
                return jsonify({"error": "No se pudo confirmar el total de la orden."}), 500

            connection.commit()

        return "", 204
    except pyodbc.Error:
        logging.exception("Error al eliminar el detalle %s", detail_id)
        return jsonify({"error": "No se pudo eliminar el detalle"}), 500



if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    initialize_database()
    app.run(host="0.0.0.0", port=5000)
