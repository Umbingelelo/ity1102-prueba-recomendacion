-- carga: clientes, faq, tickets, conversaciones
-- Caso 2 · Andesnet. Las columnas son las de datos/tratados/tablas/*.csv (las escribe preparar.py).
-- Los textos (tickets.texto, conversaciones.transcripcion) llegan ANONIMIZADOS: RUT, teléfono, correo y
-- tarjeta ya son [RUT], [TELEFONO], [CORREO] y [TARJETA] (RNF5).

CREATE TABLE IF NOT EXISTS clientes (
    cliente_id         text PRIMARY KEY,
    fecha_alta         date,
    plan               text,
    plan_descontinuado smallint,
    tipo_servicio      text,
    region             text,
    segmento           text,
    antiguedad_meses   integer,
    deuda_vigente_clp  bigint,
    saldo_a_favor_clp  bigint,
    canal_preferido    text,
    acepta_contacto    smallint NOT NULL DEFAULT 0
);

-- La base de conocimiento (RF6). El dominio responde solo con vigente = 1, duplicado = 0 y
-- plan_descontinuado = 0. Negocio puede editarla con un UPDATE, sin desplegar código (RF11).
CREATE TABLE IF NOT EXISTS faq (
    articulo_id         text PRIMARY KEY,
    pregunta            text NOT NULL,
    respuesta           text NOT NULL,
    intencion           text,
    tema                text,
    categoria_declarada text,
    vigente             smallint NOT NULL DEFAULT 0,
    duplicado           smallint NOT NULL DEFAULT 0,
    plan_descontinuado  smallint NOT NULL DEFAULT 0,
    vistas_12m          integer NOT NULL DEFAULT 0,
    ultima_edicion      date
);
CREATE INDEX IF NOT EXISTS faq_intencion ON faq (intencion, vistas_12m DESC);

-- Historia tratada. cliente_id puede no existir en clientes (huérfanos conservados): sin FOREIGN KEY.
CREATE TABLE IF NOT EXISTS tickets (
    ticket_id          text PRIMARY KEY,
    cliente_id         text,
    canal              text,
    fecha_apertura     timestamptz,
    fecha_cierre       timestamptz,
    cierre_invalido    smallint,
    categoria_original text,
    intencion          text,
    subcategoria       text,
    texto              text,
    agente_id          text,
    tiempo_espera_seg  integer,
    resuelto           smallint,
    csat               smallint CHECK (csat BETWEEN 1 AND 5),
    reabierto          smallint
);
CREATE INDEX IF NOT EXISTS tickets_cliente ON tickets (cliente_id);

CREATE TABLE IF NOT EXISTS conversaciones (
    conversacion_id   text PRIMARY KEY,
    cliente_id        text,
    canal             text,
    inicio            timestamptz,
    fin               timestamptz,
    turnos            integer,
    bucle             smallint,
    intencion_bot     text,
    derivada_a_humano smallint,
    resuelta          smallint,
    idioma            text,
    transcripcion     text
);

-- Solo en ejecución (no se carga desde CSV): el estado de cada conversación del asistente nuevo.
-- Sirve para la regla «tres intentos fallidos» (RF8) y para que una conversación derivada siga derivada.
CREATE TABLE IF NOT EXISTS sesiones_chat (
    conversacion_id   text PRIMARY KEY,
    cliente_id        text,
    canal             text,
    mensajes          integer NOT NULL DEFAULT 0,
    intentos_fallidos integer NOT NULL DEFAULT 0,
    derivada          boolean NOT NULL DEFAULT false,
    motivo_derivacion text,
    creada            timestamptz NOT NULL DEFAULT now(),
    actualizada       timestamptz NOT NULL DEFAULT now()
);
