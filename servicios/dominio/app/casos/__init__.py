"""La lógica de negocio de cada caso. Cada módulo expone lo mismo, y main.py no sabe de qué caso se trata:

    TITULO, DESCRIPCION        textos para /docs y el front
    FRONT                      campos del formulario y cómo mostrar el resultado (lo lee el front)
    Entrada                    modelo Pydantic del cuerpo de POST /api/predict (si no calza: 422)
    predecir(entrada) -> dict  con las claves:
        decision          texto corto: «bloquear», «facturacion», «recomendado»...
        probabilidad      float o None
        resultado         dict con lo que ve el usuario (se agrega a la respuesta y se guarda)
        origen            «modelo», «reserva» (el modelo no respondió) o «regla» (regla dura, sin modelo)
        version_modelo    la que devolvió la IA, o «reserva»/«regla»
        entrada_guardada  lo que se guarda como entrada (sin datos que no deban guardarse)
        llm               None, o {"instruccion": str, "contenido": dict} si hay que pedir texto al LLM
    dashboard() -> dict        métricas propias del caso para GET /api/dashboard
    router                     APIRouter con las rutas propias del caso (se montan bajo /api)
"""
