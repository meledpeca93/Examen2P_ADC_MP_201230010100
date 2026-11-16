import logging
import os
import re
from pathlib import Path

import pyodbc


APP_LOGIN = "ventasadc_app"
APP_ROLES = ("db_datareader", "db_datawriter")
GO_SEPARATOR = re.compile(r"(?im)^[ \t]*GO[ \t]*(?:--.*)?$")


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Falta la variable de entorno {name}")
    return value


def _odbc_value(value: str) -> str:
    return "{" + value.replace("}", "}}") + "}"


def _sql_literal(value: str) -> str:
    return "N'" + value.replace("'", "''") + "'"


def _connection_string(database: str, user: str, password: str) -> str:
    host = os.environ.get("DB_HOST", "db")
    port = os.environ.get("DB_PORT", "1433")
    return (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={host},{port};"
        f"DATABASE={database};"
        f"UID={user};"
        f"PWD={_odbc_value(password)};"
        "Encrypt=yes;TrustServerCertificate=yes;"
    )


def _execute_init_sql(sa_password: str) -> None:
    script_path = Path(os.environ.get("INIT_SQL_PATH", "/app/db/init.sql"))
    if not script_path.is_file():
        raise FileNotFoundError(f"No se encontró el script SQL: {script_path}")

    script = script_path.read_text(encoding="utf-8")
    batches = [batch.strip() for batch in GO_SEPARATOR.split(script) if batch.strip()]
    if not batches:
        raise RuntimeError("El script init.sql está vacío")

    connection_string = _connection_string("master", "sa", sa_password)
    with pyodbc.connect(connection_string, autocommit=True) as connection:
        cursor = connection.cursor()
        for batch in batches:
            cursor.execute(batch)


def _ensure_app_login(sa_password: str, app_password: str) -> None:
    connection_string = _connection_string("master", "sa", sa_password)
    with pyodbc.connect(connection_string, autocommit=True) as connection:
        cursor = connection.cursor()

        cursor.execute(
            "SELECT 1 FROM sys.server_principals WHERE name = ?",
            APP_LOGIN,
        )
        login_exists = cursor.fetchone() is not None
        statement = "ALTER LOGIN" if login_exists else "CREATE LOGIN"
        cursor.execute(
            f"{statement} [{APP_LOGIN}] WITH PASSWORD = {_sql_literal(app_password)}"
        )

        cursor.execute("USE [OrdenesDB]")
        cursor.execute(
            "SELECT 1 FROM sys.database_principals WHERE name = ?",
            APP_LOGIN,
        )
        if cursor.fetchone() is None:
            cursor.execute(
                f"CREATE USER [{APP_LOGIN}] FOR LOGIN [{APP_LOGIN}]"
            )

        for role in APP_ROLES:
            cursor.execute(
                """
                SELECT 1
                FROM sys.database_role_members AS membership
                JOIN sys.database_principals AS role_principal
                  ON role_principal.principal_id = membership.role_principal_id
                JOIN sys.database_principals AS member_principal
                  ON member_principal.principal_id = membership.member_principal_id
                WHERE role_principal.name = ? AND member_principal.name = ?
                """,
                role,
                APP_LOGIN,
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    f"ALTER ROLE [{role}] ADD MEMBER [{APP_LOGIN}]"
                )


def _verify_app_login(app_password: str) -> None:
    connection_string = _connection_string(
        "OrdenesDB",
        APP_LOGIN,
        app_password,
    )
    with pyodbc.connect(connection_string, autocommit=True) as connection:
        connection.cursor().execute("SELECT 1").fetchone()


def initialize_database() -> None:
    sa_password = _required_env("MSSQL_SA_PASSWORD")
    app_password = _required_env("MSSQL_APP_PASSWORD")

    logging.info("Ejecutando db/init.sql")
    _execute_init_sql(sa_password)

    logging.info("Asegurando el login y permisos de %s", APP_LOGIN)
    _ensure_app_login(sa_password, app_password)
    _verify_app_login(app_password)

    logging.info("Inicialización de OrdenesDB completada")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    initialize_database()