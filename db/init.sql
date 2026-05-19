CREATE TABLE IF NOT EXISTS artistas (
    id SERIAL PRIMARY KEY,
    nombre TEXT NOT NULL,
    apellido TEXT NOT NULL,
    genero TEXT NOT NULL,
    canciones JSONB NOT NULL DEFAULT '[]'::jsonb
);
