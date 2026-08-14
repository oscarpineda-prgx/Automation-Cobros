"""Cancelación cooperativa de operaciones largas.

Python no puede matar un hilo de forma segura: hacerlo dejaría archivos a medio escribir,
conexiones abiertas y navegadores huérfanos. Lo que sí se puede es **pedir** la parada y que
el trabajo la atienda en un punto seguro.

El contrato es de una sola pieza: quien llama pasa `cancelado`, una función sin argumentos
que devuelve `True` cuando hay que parar. Las operaciones largas la consultan en sus puntos
naturales de espera (por ejemplo, entre dos sondeos del portal) y levantan
`CancelacionSolicitada`. Quien llama la distingue de un error real y la reporta como
"cancelado por el usuario", no como fallo.

`cancelado` es siempre **opcional**: si no se pasa, el comportamiento es exactamente el de
antes. Eso permite añadir soporte de cancelación función por función sin romper nada.
"""

from __future__ import annotations

from typing import Callable

# Tipo de la señal: una función sin argumentos que dice si hay que parar.
SenalCancelacion = Callable[[], bool]


class CancelacionSolicitada(RuntimeError):
    """El usuario pidió detener la operación; no es un fallo del proceso."""


def cancelado_nunca() -> bool:
    """Señal por omisión: nunca cancela."""
    return False


def revisar(cancelado: SenalCancelacion | None, detalle: str = "") -> None:
    """Levanta `CancelacionSolicitada` si se pidió parar. No hace nada si `cancelado` es None."""
    if cancelado is not None and cancelado():
        raise CancelacionSolicitada(
            f"Operación detenida por el usuario{f' ({detalle})' if detalle else ''}."
        )
