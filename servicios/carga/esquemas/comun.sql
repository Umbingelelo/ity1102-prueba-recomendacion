-- La tabla que comparten los tres casos: cada predicción con su entrada, su resultado, la versión del
-- modelo y la fecha (EP2 §2.1), más el texto del LLM cuando llega (EP3).
CREATE TABLE IF NOT EXISTS predicciones (
    id              text PRIMARY KEY,
    creada          timestamptz NOT NULL DEFAULT now(),
    caso            text NOT NULL,
    entrada         jsonb NOT NULL,
    resultado       jsonb NOT NULL,
    decision        text NOT NULL,
    probabilidad    double precision,
    version_modelo  text NOT NULL,
    origen          text NOT NULL CHECK (origen IN ('modelo', 'reserva', 'regla')),
    latencia_ms     integer,
    estado_llm      text NOT NULL DEFAULT 'no_solicitado',
    texto_llm       text,
    motivo_llm      text,
    latencia_llm_ms integer
);
CREATE INDEX IF NOT EXISTS predicciones_creada ON predicciones (creada DESC);
CREATE INDEX IF NOT EXISTS predicciones_decision ON predicciones (decision);
