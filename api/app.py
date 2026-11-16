import logging
import os
from contextlib import closing

import pyodbc
from flask import Flask, jsonify

from init_db import _connection_string, initialize_database


app = Flask(__name__)


@app.get("/health")
def health():
    return jsonify({"status": "healthy"}), 200



# endpoint para listar las órdenes
@app.get("/api/ordenes")
def list_orders():
    try:
        connection_string = _connection_string(
            "OrdenesDB",
            "ventasadc_app",
            os.environ["MSSQL_APP_PASSWORD"],
        )
        with closing(
            pyodbc.connect(connection_string, autocommit=True)
        ) as connection:
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


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    initialize_database()
    app.run(host="0.0.0.0", port=5000)