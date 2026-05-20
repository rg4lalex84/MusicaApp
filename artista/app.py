import json
import os
import time
from datetime import date
from typing import Any

import jwt
import mysql.connector
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from mysql.connector import Error
from pydantic import BaseModel, Field

app = FastAPI(title="MS Artista")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SECRET_KEY = "musica_jwt_secret_simple"
ALGORITHM = "HS256"

DB_HOST = os.getenv("MYSQL_HOST", "localhost")
DB_PORT = int(os.getenv("MYSQL_PORT", "3306"))
DB_NAME = os.getenv("MYSQL_DB", "musica_artista_db")
DB_USER = os.getenv("MYSQL_USER", "artista_user")
DB_PASSWORD = os.getenv("MYSQL_PASSWORD", "artista_pass")


class CancionRequest(BaseModel):
    titulo: str = Field(min_length=1)
    album: str | None = None
    duracion_segundos: int | None = Field(default=None, ge=1)
    anio_lanzamiento: int | None = Field(default=None, ge=1900, le=2200)


class ArtistaRequest(BaseModel):
    nombre: str
    apellido: str
    nombre_artistico: str
    genero: str
    pais_origen: str
    fecha_nacimiento: date | None = None
    biografia: str | None = None
    canciones: list[CancionRequest] = Field(default_factory=list)


def validar_token(authorization: str | None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Falta token")

    token = authorization.split(" ", 1)[1]
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Token invalido")


def get_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )


def wait_for_db(max_retries: int = 30, delay_seconds: int = 1):
    for _ in range(max_retries):
        try:
            conn = get_connection()
            conn.close()
            return
        except Error:
            time.sleep(delay_seconds)
    raise RuntimeError("No se pudo conectar a la base de datos")


def column_exists(cur, table_name: str, column_name: str) -> bool:
    cur.execute(
        """
        SELECT COUNT(*) AS total
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
          AND column_name = %s
        """,
        (DB_NAME, table_name, column_name),
    )
    result = cur.fetchone()
    return bool(result and result["total"] > 0)


def migrate_canciones_json(cur):
    if not column_exists(cur, "artistas", "canciones"):
        return

    cur.execute("SELECT id, canciones FROM artistas")
    artistas = cur.fetchall()
    for artista in artistas:
        raw_canciones = artista.get("canciones")
        parsed: list[Any] = []

        if isinstance(raw_canciones, str):
            try:
                parsed = json.loads(raw_canciones)
            except json.JSONDecodeError:
                parsed = []
        elif isinstance(raw_canciones, list):
            parsed = raw_canciones

        for cancion in parsed:
            titulo = str(cancion).strip()
            if not titulo:
                continue
            cur.execute(
                """
                INSERT INTO canciones (artista_id, titulo, album, duracion_segundos, anio_lanzamiento)
                VALUES (%s, %s, NULL, NULL, NULL)
                ON DUPLICATE KEY UPDATE titulo = VALUES(titulo)
                """,
                (artista["id"], titulo),
            )

    cur.execute("ALTER TABLE artistas DROP COLUMN canciones")


def ensure_schema(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS artistas (
            id INT AUTO_INCREMENT PRIMARY KEY,
            nombre VARCHAR(255) NOT NULL,
            apellido VARCHAR(255) NOT NULL,
            genero VARCHAR(255) NOT NULL
        )
        """
    )

    extra_columns = {
        "nombre_artistico": "VARCHAR(255) NOT NULL DEFAULT ''",
        "pais_origen": "VARCHAR(255) NOT NULL DEFAULT 'Desconocido'",
        "fecha_nacimiento": "DATE NULL",
        "biografia": "TEXT NULL",
    }
    for column, definition in extra_columns.items():
        if not column_exists(cur, "artistas", column):
            cur.execute(f"ALTER TABLE artistas ADD COLUMN {column} {definition}")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS canciones (
            id INT AUTO_INCREMENT PRIMARY KEY,
            artista_id INT NOT NULL,
            titulo VARCHAR(255) NOT NULL,
            album VARCHAR(255) NULL,
            duracion_segundos INT NULL,
            anio_lanzamiento INT NULL,
            CONSTRAINT fk_canciones_artista
                FOREIGN KEY (artista_id) REFERENCES artistas(id)
                ON DELETE CASCADE,
            UNIQUE KEY uq_cancion_artista_titulo (artista_id, titulo)
        )
        """
    )

    migrate_canciones_json(cur)
    cur.execute("DROP TABLE IF EXISTS usuarios")


def insert_canciones(cur, artista_id: int, canciones: list[CancionRequest]):
    for cancion in canciones:
        titulo = cancion.titulo.strip()
        if not titulo:
            continue
        cur.execute(
            """
            INSERT INTO canciones (artista_id, titulo, album, duracion_segundos, anio_lanzamiento)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                artista_id,
                titulo,
                cancion.album.strip() if cancion.album else None,
                cancion.duracion_segundos,
                cancion.anio_lanzamiento,
            ),
        )


def build_artistas(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, dict[str, Any]] = {}
    for row in rows:
        artista_id = row["artista_id"]
        artista = grouped.get(artista_id)
        if not artista:
            artista = {
                "id": artista_id,
                "nombre": row["nombre"],
                "apellido": row["apellido"],
                "nombre_artistico": row["nombre_artistico"],
                "genero": row["genero"],
                "pais_origen": row["pais_origen"],
                "fecha_nacimiento": row["fecha_nacimiento"],
                "biografia": row["biografia"],
                "canciones": [],
            }
            grouped[artista_id] = artista

        if row["cancion_id"] is not None:
            artista["canciones"].append(
                {
                    "id": row["cancion_id"],
                    "titulo": row["titulo"],
                    "album": row["album"],
                    "duracion_segundos": row["duracion_segundos"],
                    "anio_lanzamiento": row["anio_lanzamiento"],
                }
            )

    return list(grouped.values())


def fetch_artistas(cur, artista_id: int | None = None):
    query = """
        SELECT
            a.id AS artista_id,
            a.nombre,
            a.apellido,
            a.nombre_artistico,
            a.genero,
            a.pais_origen,
            a.fecha_nacimiento,
            a.biografia,
            c.id AS cancion_id,
            c.titulo,
            c.album,
            c.duracion_segundos,
            c.anio_lanzamiento
        FROM artistas a
        LEFT JOIN canciones c ON c.artista_id = a.id
    """
    params: tuple[Any, ...] = ()
    if artista_id is not None:
        query += " WHERE a.id = %s"
        params = (artista_id,)
    query += " ORDER BY a.id ASC, c.id ASC"
    cur.execute(query, params)
    return build_artistas(cur.fetchall())


@app.on_event("startup")
def startup():
    wait_for_db()
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    ensure_schema(cur)
    conn.commit()
    cur.close()
    conn.close()


@app.get("/")
def home():
    return {"service": "artista", "status": "ok"}


@app.get("/artistas")
def listar_artistas(authorization: str | None = Header(default=None)):
    validar_token(authorization)
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    artistas = fetch_artistas(cur)
    cur.close()
    conn.close()
    return artistas


@app.get("/artistas/{artista_id}")
def obtener_artista(artista_id: int, authorization: str | None = Header(default=None)):
    validar_token(authorization)
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    artistas = fetch_artistas(cur, artista_id=artista_id)
    cur.close()
    conn.close()
    if not artistas:
        raise HTTPException(status_code=404, detail="Artista no encontrado")
    return artistas[0]


@app.post("/artistas")
def crear_artista(data: ArtistaRequest, authorization: str | None = Header(default=None)):
    validar_token(authorization)
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        INSERT INTO artistas (
            nombre,
            apellido,
            nombre_artistico,
            genero,
            pais_origen,
            fecha_nacimiento,
            biografia
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            data.nombre,
            data.apellido,
            data.nombre_artistico,
            data.genero,
            data.pais_origen,
            data.fecha_nacimiento,
            data.biografia,
        ),
    )
    artista_id = cur.lastrowid
    insert_canciones(cur, artista_id, data.canciones)
    conn.commit()

    artistas = fetch_artistas(cur, artista_id=artista_id)
    cur.close()
    conn.close()
    return artistas[0]


@app.put("/artistas/{artista_id}")
def actualizar_artista(
    artista_id: int,
    data: ArtistaRequest,
    authorization: str | None = Header(default=None),
):
    validar_token(authorization)
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id FROM artistas WHERE id = %s", (artista_id,))
    existe = cur.fetchone()
    if not existe:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Artista no encontrado")

    cur.execute(
        """
        UPDATE artistas
        SET
            nombre = %s,
            apellido = %s,
            nombre_artistico = %s,
            genero = %s,
            pais_origen = %s,
            fecha_nacimiento = %s,
            biografia = %s
        WHERE id = %s
        """,
        (
            data.nombre,
            data.apellido,
            data.nombre_artistico,
            data.genero,
            data.pais_origen,
            data.fecha_nacimiento,
            data.biografia,
            artista_id,
        ),
    )
    cur.execute("DELETE FROM canciones WHERE artista_id = %s", (artista_id,))
    insert_canciones(cur, artista_id, data.canciones)
    conn.commit()

    artistas = fetch_artistas(cur, artista_id=artista_id)
    cur.close()
    conn.close()
    return artistas[0]


@app.delete("/artistas/{artista_id}")
def eliminar_artista(artista_id: int, authorization: str | None = Header(default=None)):
    validar_token(authorization)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM artistas WHERE id = %s", (artista_id,))
    deleted = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()

    if deleted == 0:
        raise HTTPException(status_code=404, detail="Artista no encontrado")
    return {"deleted": True}
