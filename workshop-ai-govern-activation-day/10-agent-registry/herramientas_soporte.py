"""Herramienta y fábrica del especialista de soporte técnico de TechStore.

Es el mismo especialista del Módulo 9. Aquí lo usa servidor_soporte_tecnico.py
para exponerlo como servicio A2A, que el Módulo 10 publica en AWS Agent Registry.
"""

from strands import Agent, tool

# --- Base de conocimiento simulada ---

PROBLEMAS_CONOCIDOS = {
    "auriculares": "Fallo de emparejamiento Bluetooth 5.0 con teléfonos antiguos. Solución: mantener pulsado "
    "el botón de encendido 10 segundos para restablecerlos y volver a emparejarlos.",
    "hub": "Algunos portátiles necesitan USB-C con modo alternativo DisplayPort para usar monitores externos. "
    "Solución: comprobar las especificaciones del portátil o usar un puerto Thunderbolt.",
    "teclado": "El firmware v2.1 provoca pulsaciones fantasma. Solución: actualizar al firmware v2.3 desde la "
    "web del fabricante.",
}


@tool
def buscar_problemas_conocidos(dispositivo: str) -> str:
    """Busca problemas conocidos y su solución para un dispositivo de la tienda.

    Args:
        dispositivo: Nombre del dispositivo (por ejemplo "Auriculares Inalámbricos")
    """
    for palabra_clave, solucion in PROBLEMAS_CONOCIDOS.items():
        if palabra_clave in dispositivo.lower():
            return f"Problema conocido ({palabra_clave}): {solucion}"
    return (
        f"No hay problemas conocidos para '{dispositivo}'. "
        "Recomienda reiniciar el dispositivo, revisar las conexiones y actualizar el firmware."
    )


def crear_soporte_tecnico(context_id: str | None = None) -> Agent:
    """Crea el especialista de soporte técnico.

    Args:
        context_id: ID de la conversación A2A. El servidor A2A llama a esta función
            una vez por conversación para que cada cliente tenga su propio agente.
    """
    return Agent(
        name="soporte_tecnico",
        description="Especialista de TechStore que diagnostica problemas de dispositivos "
        "electrónicos y propone soluciones paso a paso.",
        system_prompt="""Eres el especialista de soporte técnico de TechStore, una tienda de electrónica.
Usa buscar_problemas_conocidos para diagnosticar el dispositivo del cliente.
Responde en español con un diagnóstico breve y de 2 a 4 pasos concretos para resolverlo.""",
        tools=[buscar_problemas_conocidos],
        callback_handler=None,
    )
