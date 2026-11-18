-- carga: usuarios, dispositivos, lista_negra, transacciones
-- Caso 3 · Kipu Pagos. Las columnas son las de datos/tratados/tablas/*.csv (las escribe preparar.py).
-- El número de tarjeta no está en ninguna tabla (RNF5).

CREATE TABLE IF NOT EXISTS usuarios (
    usuario_id            text PRIMARY KEY,
    fecha_registro        date,
    pais                  char(2),
    segmento              text,
    nivel_kyc             smallint CHECK (nivel_kyc BETWEEN 0 AND 3),
    verificado            smallint,
    telefono_verificado   smallint,
    edad_cuenta_dias      integer,
    transacciones_previas integer,
    email_desechable      smallint
);

CREATE TABLE IF NOT EXISTS dispositivos (
    dispositivo_id     text PRIMARY KEY,
    tipo               text,
    usuarios_distintos integer,
    emulador           smallint,
    pais_declarado     char(2)
);

CREATE TABLE IF NOT EXISTS lista_negra (
    tipo       text NOT NULL,
    valor      text NOT NULL,
    motivo     text,
    fecha_alta date,
    vigente    smallint NOT NULL DEFAULT 1,
    PRIMARY KEY (tipo, valor)
);

-- Historia tratada. usuario_id puede no existir en usuarios (huérfanos conservados): sin FOREIGN KEY.
CREATE TABLE IF NOT EXISTS transacciones (
    transaccion_id      text PRIMARY KEY,
    usuario_id          text,
    comercio_id         text,
    dispositivo_id      text,
    ts_local            timestamptz,
    hora_local          smallint,
    monto_clp           double precision,
    moneda_original     char(3),
    canal               text,
    pais_transaccion    char(2),
    intentos_previos_1h integer,
    latitud             double precision,
    longitud            double precision,
    es_reintento        smallint,
    es_fraude           smallint
);
CREATE INDEX IF NOT EXISTS transacciones_usuario ON transacciones (usuario_id);
