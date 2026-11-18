"""Costo mensual del sistema de EP3 al volumen de TU caso (apartado 3 del informe y pregunta del IE6).

    python3 herramientas/costos.py                                  # con los valores por defecto de tu caso
    python3 herramientas/costos.py --latencia-ms 45 --memoria-mb 2048   # con TU ModelLatency medido
    python3 herramientas/costos.py --ayuda-volumen                  # de dónde sale el volumen de cada caso

Imprime una tabla en Markdown lista para pegar, y la comparación con las alternativas que pide EP3 §1
(endpoint de tiempo real, modelo dentro del contenedor, Bedrock). Solo usa la biblioteca estándar.

Precios: lista de precios pública de AWS para us-east-1, revisada el 17-11-2026 (SageMaker: archivo
offers/v1.0/aws/AmazonSageMaker/current/us-east-1/index.csv). Los precios cambian: antes de entregar,
confírmalos en https://calculator.aws y pon ese link en el informe.
"""
import argparse
from pathlib import Path

HORAS_MES = 730
PRECIOS = {
    "ec2_t3_medium_hora": 0.0416,         # EC2 On-Demand Linux
    "ipv4_publica_hora": 0.005,           # toda IPv4 pública, asociada o no (desde feb-2024)
    "ebs_gp3_gb_mes": 0.08,
    "sm_serverless_gb_segundo": 0.00002,  # USE1-ServerlessInf:Mem-1GB = 0,00002 USD/s; 2 GB = 0,00004 ...
    "sm_tiempo_real_t2_medium_hora": 0.056,   # USE1-Host:ml.t2.medium
    "sm_entrenamiento_m5_large_hora": 0.115,  # USE1-Train:ml.m5.large
    "s3_gb_mes": 0.023,
    "cloudwatch_logs_ingesta_gb": 0.50,
    "cloudwatch_logs_guardado_gb_mes": 0.03,
}

# Volumen mensual de cada caso, sacado de su documento. DESAFÍO: revisa estos supuestos y cítalos.
VOLUMEN = {
    "fraude": {"predicciones": 200_000 * 30, "textos_llm": int(200_000 * 30 * 0.024),
               "nota": "200.000 tx/día (sección 2 del caso); el LLM solo para lo que va a revisión: 2,4% del tráfico",
               "presupuesto": 6000},
    "recomendacion": {"predicciones": 100_000 * 10, "textos_llm": int(38_400 * 0.6),
                      "nota": "100.000 usuarios activos/mes × ~10 pedidos de recomendación; campañas: 38.400 clientes "
                              "con compra × ~60% con consentimiento, una al mes",
                      "presupuesto": 3000 - 780},
    "chatbot": {"predicciones": 340_000 * 4, "textos_llm": int(340_000 * 4 * 0.75),
                "nota": "340.000 contactos/mes × ~4 mensajes; el LLM redacta los ~75% que no se derivan",
                "presupuesto": 8500},
}


def main():
    raiz = Path(__file__).resolve().parent.parent
    caso_defecto = (raiz / "CASO").read_text().strip() if (raiz / "CASO").exists() else "fraude"
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--caso", default=caso_defecto, choices=VOLUMEN)
    p.add_argument("--predicciones", type=int, help="invocaciones al mes (por defecto, las del caso)")
    p.add_argument("--textos-llm", type=int, help="textos del LLM al mes (por defecto, los del caso)")
    p.add_argument("--latencia-ms", type=float, default=50, help="duración promedio facturada: ModelLatency medido")
    p.add_argument("--memoria-mb", type=int, default=2048, help="memoria del endpoint serverless")
    p.add_argument("--tokens-entrada", type=int, default=600, help="tokens por texto enviado al LLM")
    p.add_argument("--tokens-salida", type=int, default=150, help="tokens por respuesta del LLM")
    p.add_argument("--llm-entrada-1m", type=float, default=0.20,
                   help="USD por millón de tokens de entrada del proveedor pagado que elijas (referencia: modelo chico)")
    p.add_argument("--llm-salida-1m", type=float, default=0.20, help="USD por millón de tokens de salida")
    p.add_argument("--lineas-log", type=int, default=4, help="líneas de log por predicción (gateway, dominio, ia...)")
    p.add_argument("--ayuda-volumen", action="store_true")
    a = p.parse_args()
    v = VOLUMEN[a.caso]
    if a.ayuda_volumen:
        print(f"{a.caso}: {v['nota']}")
        return
    n = a.predicciones or v["predicciones"]
    textos = a.textos_llm if a.textos_llm is not None else v["textos_llm"]
    gb = a.memoria_mb / 1024
    P = PRECIOS

    filas = [
        ("EC2 t3.medium (servidor)", f"{HORAS_MES} h × {P['ec2_t3_medium_hora']}", P["ec2_t3_medium_hora"] * HORAS_MES),
        ("IPv4 pública (IP elástica)", f"{HORAS_MES} h × {P['ipv4_publica_hora']}", P["ipv4_publica_hora"] * HORAS_MES),
        ("Disco EBS gp3 20 GB", f"20 × {P['ebs_gp3_gb_mes']}", 20 * P["ebs_gp3_gb_mes"]),
        ("SageMaker serverless",
         f"{n:,} inv × {a.latencia_ms:g} ms × {gb:g} GB × {P['sm_serverless_gb_segundo']}/GB·s".replace(",", "."),
         n * a.latencia_ms / 1000 * gb * P["sm_serverless_gb_segundo"]),
        ("SageMaker: reentrenar 4 veces al mes", f"4 × 5 min × {P['sm_entrenamiento_m5_large_hora']}/h",
         4 * 5 / 60 * P["sm_entrenamiento_m5_large_hora"]),
        ("S3 (datos tratados y modelos)", f"1 GB × {P['s3_gb_mes']}", 1 * P["s3_gb_mes"]),
        ("CloudWatch Logs",
         f"{n * a.lineas_log * 400 / 1e9:.1f} GB × ({P['cloudwatch_logs_ingesta_gb']} + {P['cloudwatch_logs_guardado_gb_mes']})",
         n * a.lineas_log * 400 / 1e9 * (P["cloudwatch_logs_ingesta_gb"] + P["cloudwatch_logs_guardado_gb_mes"])),
        ("LLM en un proveedor pagado",
         f"{textos:,} textos × ({a.tokens_entrada}×{a.llm_entrada_1m} + {a.tokens_salida}×{a.llm_salida_1m})/1M".replace(",", "."),
         textos * (a.tokens_entrada * a.llm_entrada_1m + a.tokens_salida * a.llm_salida_1m) / 1e6),
    ]
    total = sum(f[2] for f in filas)
    print(f"## Costo mensual · caso {a.caso}\n\nVolumen: {v['nota']}.\n")
    print("| Componente | Cálculo | USD/mes |\n|---|---|---|")
    for nombre, calculo, usd in filas:
        print(f"| {nombre} | {calculo} | {usd:,.2f} |")
    print(f"| **Total** | | **{total:,.2f}** |")
    print(f"\nPresupuesto del caso: USD {v['presupuesto']:,}/mes → se usa el {100 * total / v['presupuesto']:.1f}%.")

    sm_serverless = filas[3][2]
    tiempo_real = P["sm_tiempo_real_t2_medium_hora"] * HORAS_MES
    equilibrio = tiempo_real / (a.latencia_ms / 1000 * gb * P["sm_serverless_gb_segundo"])
    print("\n## Alternativas para servir el modelo (IE6)\n")
    print("| Opción | USD/mes | A favor | En contra |\n|---|---|---|---|")
    print(f"| Serverless {a.memoria_mb} MB (la elegida) | {sm_serverless:,.2f} | Paga solo lo que se usa; escala solo | Cold start (~0,5–6 s) después de minutos sin uso |")
    print(f"| Tiempo real ml.t2.medium, 1 instancia | {tiempo_real:,.2f} | Sin cold start, latencia estable | Paga 730 h aunque no haya tráfico; para alta disponibilidad son 2 (× 2) |")
    print("| Modelo dentro del contenedor (EP2) | 0 extra (usa la CPU de la EC2) | La menor latencia: sin red | Escalar el modelo obliga a escalar el servicio; cambiar el modelo es desplegar |")
    print("| Amazon Bedrock | no aplica | Modelos fundacionales administrados | No sirve tu XGBoost propio: es para LLM; además no está en el Learner Lab |")
    print(f"\nPunto de equilibrio: el serverless es más barato que una ml.t2.medium encendida mientras haya menos de "
          f"{equilibrio:,.0f} invocaciones al mes con esta latencia y memoria.".replace(",", "."))


if __name__ == "__main__":
    main()
