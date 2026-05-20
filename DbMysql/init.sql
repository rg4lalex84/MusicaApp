CREATE TABLE IF NOT EXISTS artistas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(255) NOT NULL,
    apellido VARCHAR(255) NOT NULL,
    nombre_artistico VARCHAR(255) NOT NULL DEFAULT '',
    genero VARCHAR(255) NOT NULL,
    pais_origen VARCHAR(255) NOT NULL DEFAULT 'Desconocido',
    fecha_nacimiento DATE NULL,
    biografia TEXT NULL
);

CREATE TABLE IF NOT EXISTS canciones (
    id INT AUTO_INCREMENT PRIMARY KEY,
    artista_id INT NOT NULL,
    titulo VARCHAR(255) NOT NULL,
    album VARCHAR(255) NULL,
    duracion_segundos INT NULL,
    anio_lanzamiento INT NULL,
    CONSTRAINT fk_canciones_artista
        FOREIGN KEY (artista_id) REFERENCES artistas(id)
        ON DELETE CASCADE
);
