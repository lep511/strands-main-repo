"""Servidor A2A: expone al especialista de soporte técnico como un servicio independiente.

Uso (desde esta carpeta):

    python servidor_soporte_tecnico.py          # puerto 9000
    python servidor_soporte_tecnico.py 9100     # otro puerto

Agent Card: http://127.0.0.1:<puerto>/.well-known/agent-card.json
"""

import logging
import sys

from strands.multiagent.a2a import A2AServer

from herramientas_soporte import crear_soporte_tecnico

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")

if __name__ == "__main__":
    puerto = int(sys.argv[1]) if len(sys.argv) > 1 else 9000
    servidor = A2AServer(
        agent_factory=crear_soporte_tecnico,  # un agente nuevo por conversación (context_id)
        host="127.0.0.1",
        port=puerto,
        # Dejamos el streaming por defecto: con enable_a2a_compliant_streaming=True, A2AAgent (Strands 1.62)
        # devuelve cada fragmento de la respuesta como un bloque de texto separado.
    )
    servidor.serve()
