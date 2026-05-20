CREATE TABLE IF NOT EXISTS usuarios_auth (
    id SERIAL PRIMARY KEY,
    usuario VARCHAR(100) NOT NULL UNIQUE,
    nombre VARCHAR(255) NOT NULL,
    apellido VARCHAR(255) NOT NULL,
    password VARCHAR(255) NOT NULL
);

INSERT INTO usuarios_auth (usuario, nombre, apellido, password)
VALUES ('admin', 'Admin', 'Principal', '123456')
ON CONFLICT (usuario) DO NOTHING;
