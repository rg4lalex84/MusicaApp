import os
import time
import json
from typing import List

import jwt
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import mysql.connector
from mysql.connector import Error

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


class ArtistaRequest(BaseModel):
    nombre: str
    apellido: str
    genero: str
    canciones: List[str] = []


class UsuarioRequest(BaseModel):
    usuario: str
    nombre: str
    apellido: str
    password: str


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


@app.on_event("startup")
def startup():
    wait_for_db()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS artistas (
            id INT AUTO_INCREMENT PRIMARY KEY,
            nombre VARCHAR(255) NOT NULL,
            apellido VARCHAR(255) NOT NULL,
            genero VARCHAR(255) NOT NULL,
            canciones JSON NOT NULL
        );
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id INT AUTO_INCREMENT PRIMARY KEY,
            usuario VARCHAR(100) NOT NULL UNIQUE,
            nombre VARCHAR(255) NOT NULL,
            apellido VARCHAR(255) NOT NULL,
            password VARCHAR(255) NOT NULL
        );
        """
    )
    conn.commit()
    cur.close()
    conn.close()


@app.get("/")
def home():
    return {"service": "artista", "status": "ok"}


@app.get("/usuarios")
def listar_usuarios(authorization: str | None = Header(default=None)):
    validar_token(authorization)
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, usuario, nombre, apellido FROM usuarios ORDER BY id ASC")
    usuarios = cur.fetchall()
    cur.close()
    conn.close()
    return usuarios


@app.post("/usuarios")
def crear_usuario(data: UsuarioRequest, authorization: str | None = Header(default=None)):
    validar_token(authorization)
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            """
            INSERT INTO usuarios (usuario, nombre, apellido, password)
            VALUES (%s, %s, %s, %s)
            """,
            (data.usuario, data.nombre, data.apellido, data.password),
        )
        usuario_id = cur.lastrowid
        cur.execute(
            "SELECT id, usuario, nombre, apellido FROM usuarios WHERE id = %s",
            (usuario_id,),
        )
        usuario = cur.fetchone()
        conn.commit()
        return usuario
    except Error as exc:
        if exc.errno == 1062:
            raise HTTPException(status_code=400, detail="El usuario ya existe")
        raise
    finally:
        cur.close()
        conn.close()


@app.get("/artistas")
def listar_artistas(authorization: str | None = Header(default=None)):
    validar_token(authorization)
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT id, nombre, apellido, genero, canciones FROM artistas ORDER BY id ASC"
    )
    artistas = cur.fetchall()
    cur.close()
    conn.close()
    for artista in artistas:
        if isinstance(artista["canciones"], str):
            artista["canciones"] = json.loads(artista["canciones"])
    return artistas


@app.get("/artistas/{artista_id}")
def obtener_artista(artista_id: int, authorization: str | None = Header(default=None)):
    validar_token(authorization)
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT id, nombre, apellido, genero, canciones FROM artistas WHERE id = %s",
        (artista_id,),
    )
    artista = cur.fetchone()
    cur.close()
    conn.close()
    if artista:
        if isinstance(artista["canciones"], str):
            artista["canciones"] = json.loads(artista["canciones"])
        return artista
    raise HTTPException(status_code=404, detail="Artista no encontrado")


@app.post("/artistas")
def crear_artista(data: ArtistaRequest, authorization: str | None = Header(default=None)):
    validar_token(authorization)
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        INSERT INTO artistas (nombre, apellido, genero, canciones)
        VALUES (%s, %s, %s, %s)
        """,
        (data.nombre, data.apellido, data.genero, json.dumps(data.canciones)),
    )
    artista_id = cur.lastrowid
    cur.execute(
        "SELECT id, nombre, apellido, genero, canciones FROM artistas WHERE id = %s",
        (artista_id,),
    )
    artista = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if isinstance(artista["canciones"], str):
        artista["canciones"] = json.loads(artista["canciones"])
    return artista


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
        SET nombre = %s, apellido = %s, genero = %s, canciones = %s
        WHERE id = %s
        """,
        (
            data.nombre,
            data.apellido,
            data.genero,
            json.dumps(data.canciones),
            artista_id,
        ),
    )
    cur.execute(
        "SELECT id, nombre, apellido, genero, canciones FROM artistas WHERE id = %s",
        (artista_id,),
    )
    artista = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if isinstance(artista["canciones"], str):
        artista["canciones"] = json.loads(artista["canciones"])
    return artista


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
