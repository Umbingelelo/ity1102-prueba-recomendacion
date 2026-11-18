"""Código que comparten el tratamiento de datos y los servicios.

Todo lo que está aquí se usa en dos lugares: al entrenar (datos/preparar.py, modelo/entrenar.py) y al
servir (servicios/ia, servicios/dominio). Si las variables se calcularan de dos formas distintas, el
modelo vería en producción algo distinto de lo que vio al entrenar. Por eso viven una sola vez.
Solo usa la biblioteca estándar: entra en cualquier imagen sin agregar dependencias.
"""
