import os
import time
from datetime import datetime, timedelta, timezone

import jwt
import psycopg2
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from psycopg2 import Error, OperationalError
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel, Field

app = FastAPI(title="MS Auth")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SECRET_KEY = "musica_jwt_secret_simple"
ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = 60

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "musica_db")
DB_USER = os.getenv("DB_USER", "musica_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "musica_pass")

DEFAULT_ADMIN_USER = "admin"
DEFAULT_ADMIN_PASSWORD = "123456"


class LoginRequest(BaseModel):
    username: str
    password: str


class VerifyRequest(BaseModel):
    token: str


class UsuarioCreateRequest(BaseModel):
    usuario: str
    nombre: str
    apellido: str
    password: str = Field(min_length=4)


class UsuarioUpdateRequest(BaseModel):
    usuario: str
    nombre: str
    apellido: str


class UsuarioPasswordRequest(BaseModel):
    password_nueva: str = Field(min_length=4)
    password_actual: str | None = None


def get_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )


def wait_for_db(max_retries: int = 30, delay_seconds: int = 1):
    for _ in range(max_retries):
        try:
            conn = get_connection()
            conn.close()
            return
        except OperationalError:
            time.sleep(delay_seconds)
    raise RuntimeError("No se pudo conectar a la base de datos")


def validar_token(authorization: str | None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Falta token")

    token = authorization.split(" ", 1)[1]
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Token invalido")


@app.on_event("startup")
def startup():
    wait_for_db()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios_auth (
            id SERIAL PRIMARY KEY,
            usuario VARCHAR(100) NOT NULL UNIQUE,
            nombre VARCHAR(255) NOT NULL,
            apellido VARCHAR(255) NOT NULL,
            password VARCHAR(255) NOT NULL
        );
        """
    )
    cur.execute(
        """
        INSERT INTO usuarios_auth (usuario, nombre, apellido, password)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (usuario) DO NOTHING
        """,
        (DEFAULT_ADMIN_USER, "Admin", "Principal", DEFAULT_ADMIN_PASSWORD),
    )
    conn.commit()
    cur.close()
    conn.close()


@app.get("/")
def home():
    return {"service": "auth", "status": "ok"}


@app.post("/login")
def login(data: LoginRequest):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(
        """
        SELECT id, usuario, password
        FROM usuarios_auth
        WHERE usuario = %s
        """,
        (data.username,),
    )
    user = cur.fetchone()
    cur.close()
    conn.close()

    if not user or user["password"] != data.password:
        raise HTTPException(status_code=401, detail="Credenciales invalidas")

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_MINUTES)
    payload = {
        "sub": user["usuario"],
        "user_id": user["id"],
        "exp": expires_at,
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return {"access_token": token, "token_type": "bearer"}


@app.post("/verify")
def verify(data: VerifyRequest):
    try:
        payload = jwt.decode(data.token, SECRET_KEY, algorithms=[ALGORITHM])
        return {"valid": True, "payload": payload}
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Token invalido")


@app.get("/usuarios")
def listar_usuarios(authorization: str | None = Header(default=None)):
    validar_token(authorization)
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(
        """
        SELECT id, usuario, nombre, apellido
        FROM usuarios_auth
        ORDER BY id ASC
        """
    )
    usuarios = cur.fetchall()
    cur.close()
    conn.close()
    return usuarios


@app.post("/usuarios")
def crear_usuario(data: UsuarioCreateRequest, authorization: str | None = Header(default=None)):
    validar_token(authorization)
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            INSERT INTO usuarios_auth (usuario, nombre, apellido, password)
            VALUES (%s, %s, %s, %s)
            RETURNING id, usuario, nombre, apellido
            """,
            (data.usuario, data.nombre, data.apellido, data.password),
        )
        usuario = cur.fetchone()
        conn.commit()
        return usuario
    except Error as exc:
        if exc.pgcode == "23505":
            raise HTTPException(status_code=400, detail="El usuario ya existe")
        raise
    finally:
        cur.close()
        conn.close()


@app.put("/usuarios/{usuario_id}")
def editar_usuario(
    usuario_id: int,
    data: UsuarioUpdateRequest,
    authorization: str | None = Header(default=None),
):
    validar_token(authorization)
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT id FROM usuarios_auth WHERE id = %s", (usuario_id,))
        existe = cur.fetchone()
        if not existe:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        cur.execute(
            """
            UPDATE usuarios_auth
            SET usuario = %s, nombre = %s, apellido = %s
            WHERE id = %s
            RETURNING id, usuario, nombre, apellido
            """,
            (data.usuario, data.nombre, data.apellido, usuario_id),
        )
        usuario = cur.fetchone()
        conn.commit()
        return usuario
    except Error as exc:
        if exc.pgcode == "23505":
            raise HTTPException(status_code=400, detail="El usuario ya existe")
        raise
    finally:
        cur.close()
        conn.close()


@app.put("/usuarios/{usuario_id}/password")
def cambiar_password(
    usuario_id: int,
    data: UsuarioPasswordRequest,
    authorization: str | None = Header(default=None),
):
    validar_token(authorization)
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            "SELECT id, password FROM usuarios_auth WHERE id = %s",
            (usuario_id,),
        )
        usuario = cur.fetchone()
        if not usuario:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        if data.password_actual is not None and data.password_actual != usuario["password"]:
            raise HTTPException(status_code=400, detail="Password actual incorrecta")

        if data.password_nueva == usuario["password"]:
            raise HTTPException(
                status_code=400,
                detail="La nueva password debe ser diferente a la actual",
            )

        cur.execute(
            "UPDATE usuarios_auth SET password = %s WHERE id = %s",
            (data.password_nueva, usuario_id),
        )
        conn.commit()
        return {"updated": True}
    finally:
        cur.close()
        conn.close()


@app.delete("/usuarios/{usuario_id}")
def eliminar_usuario(usuario_id: int, authorization: str | None = Header(default=None)):
    payload = validar_token(authorization)
    if payload.get("user_id") == usuario_id:
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propio usuario")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM usuarios_auth WHERE id = %s", (usuario_id,))
    deleted = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()

    if deleted == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    return {"deleted": True}
