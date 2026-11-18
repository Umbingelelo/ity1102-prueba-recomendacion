-- carga: productos, usuarios, transacciones, perfil_usuario_categoria
-- Caso 1 · Nexus Retail. Las columnas son las de datos/tratados/tablas/*.csv (las escribe preparar.py).
-- No hay correo, nombre, dirección ni RUT en ninguna tabla (RNF7); la comuna tampoco se guarda.
-- El clickstream tratado no se carga: solo alimenta las variables del modelo.

CREATE TABLE IF NOT EXISTS productos (
    sku                text PRIMARY KEY,
    nombre             text,
    categoria          text,
    marca              text,
    precio             integer,            -- nulo = en edición en el ERP: no se recomienda
    stock              integer,            -- nulo = el ERP mandó «ERROR»: no se recomienda (RF5)
    activo             smallint,
    costo_sobre_precio smallint,
    fecha_alta         date,
    ventas_90d         integer NOT NULL DEFAULT 0,   -- unidades vendidas en los 90 días previos a la extracción
    ventas_total       integer NOT NULL DEFAULT 0
);
-- La lista de más vendidos (RF8, RNF3) se pide en cada respuesta de reserva: tiene que ser barata
CREATE INDEX IF NOT EXISTS productos_mas_vendidos ON productos (ventas_90d DESC, sku) WHERE activo = 1 AND stock > 0;
CREATE INDEX IF NOT EXISTS productos_categoria ON productos (categoria, ventas_90d DESC);

CREATE TABLE IF NOT EXISTS usuarios (
    usuario_id       text PRIMARY KEY,
    fecha_registro   date,
    region           text,
    canal_captacion  text,
    email_valido     smallint,
    acepta_marketing smallint,             -- 1 sí, 0 no, nulo = no se preguntó (RN2: solo 1 se personaliza)
    edad             smallint
);

-- Historia tratada. pedido_id se repite (un pedido tiene varias líneas): la clave es pedido + línea.
-- usuario_id puede ser nulo (invitado) o no existir en usuarios (huérfano conservado): sin FOREIGN KEY.
CREATE TABLE IF NOT EXISTS transacciones (
    pedido_id       text NOT NULL,
    linea           smallint NOT NULL,
    usuario_id      text,
    sku             text,
    categoria       text,
    fecha           timestamptz,
    cantidad        integer,
    precio_unitario integer,
    descuento       integer,
    total           integer,
    total_cuadra    smallint,
    canal           text,
    estado          text,
    es_venta        smallint NOT NULL,
    PRIMARY KEY (pedido_id, linea)
);
CREATE INDEX IF NOT EXISTS transacciones_usuario ON transacciones (usuario_id, fecha DESC);

-- Las variables del modelo por usuario y categoría, calculadas con toda la historia (misma función que
-- el entrenamiento). Solo usuarios con consentimiento explícito. El dominio manda estas filas a la IA.
CREATE TABLE IF NOT EXISTS perfil_usuario_categoria (
    usuario_id               text NOT NULL,
    categoria                text NOT NULL,
    compras_cat              integer,
    unidades_cat             integer,
    gasto_cat                bigint,
    dias_desde_ultima_cat    integer,      -- nulo = nunca compró en la categoría
    compras_cat_90d          integer,
    share_cat                double precision,
    compras_totales          integer,
    dias_desde_ultima_compra integer,
    vistas_cat               integer,
    clics_cat                integer,
    carrito_cat              integer,
    popularidad_cat          double precision,
    PRIMARY KEY (usuario_id, categoria)
);
