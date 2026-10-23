"""Servidor MCP del equipo de Pedidos de TechStore.

Expone dos herramientas de solo lectura sobre los pedidos de la tienda. En el
Módulo 10 este servidor se publica en AWS Agent Registry como un registro de
tipo MCP, y los agentes lo descubren desde allí en lugar de tenerlo cableado.

Uso (desde esta carpeta):

    python servidor_mcp_pedidos.py          # puerto 8000
    python servidor_mcp_pedidos.py 8100     # otro puerto

Endpoint MCP (streamable HTTP): http://127.0.0.1:<puerto>/mcp
"""

import sys
from datetime import date, timedelta

from mcp.server.mcpserver import MCPServer


def hace(dias: int) -> str:
    """Fecha relativa a hoy, para que los plazos de devolución den el mismo resultado cualquier día."""
    return (date.today() - timedelta(days=dias)).isoformat()


# --- Datos simulados ---

PEDIDOS = {
    "ORD-5521": {"producto": "Auriculares Inalámbricos", "importe": 89.99, "estado": "entregado", "fecha_entrega": hace(14)},
    "ORD-7788": {"producto": "Teclado Mecánico", "importe": 129.00, "estado": "entregado", "fecha_entrega": hace(8)},
    "ORD-3120": {"producto": "Monitor 4K", "importe": 279.00, "estado": "entregado", "fecha_entrega": hace(45)},
    "ORD-9034": {"producto": "Hub USB-C", "importe": 45.50, "estado": "en camino", "fecha_entrega": None},
}

ENVIOS = {
    "ORD-5521": {"transportista": "RápidoExpress", "seguimiento": "RX-55210", "ultimo_evento": "Entregado en buzón"},
    "ORD-7788": {"transportista": "RápidoExpress", "seguimiento": "RX-77880", "ultimo_evento": "Entregado en mano"},
    "ORD-3120": {"transportista": "EnvíaYa", "seguimiento": "EY-31200", "ultimo_evento": "Entregado en mano"},
    "ORD-9034": {
        "transportista": "EnvíaYa",
        "seguimiento": "EY-90340",
        "ultimo_evento": f"En el centro de reparto de Madrid. Entrega prevista: {hace(-2)}",
    },
}

servidor = MCPServer(
    name="techstore-pedidos",
    instructions="Consulta pedidos y envíos de TechStore. Solo lectura.",
)


@servidor.tool()
def consultar_pedido(pedido_id: str) -> dict:
    """Devuelve el producto, el importe, el estado y la fecha de entrega de un pedido de TechStore.

    Args:
        pedido_id: Identificador del pedido, por ejemplo "ORD-5521"
    """
    pedido = PEDIDOS.get(pedido_id.strip().upper())
    if pedido is None:
        return {"error": f"No existe el pedido {pedido_id}"}
    return {"pedido_id": pedido_id.upper(), **pedido}


@servidor.tool()
def consultar_envio(pedido_id: str) -> dict:
    """Devuelve el transportista, el número de seguimiento y el último evento del envío de un pedido.

    Args:
        pedido_id: Identificador del pedido, por ejemplo "ORD-9034"
    """
    envio = ENVIOS.get(pedido_id.strip().upper())
    if envio is None:
        return {"error": f"No hay datos de envío para el pedido {pedido_id}"}
    return {"pedido_id": pedido_id.upper(), **envio}


if __name__ == "__main__":
    puerto = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    servidor.run(transport="streamable-http", host="127.0.0.1", port=puerto)
