# Gobierno de IA en AWS

Los agentes de IA toman decisiones, llaman a herramientas e interactúan con clientes, a menudo con poca supervisión. Sin gobierno, una sola inyección de prompt puede engañar a un agente para aprobar transacciones fraudulentas, filtrar datos de clientes o saltarse las reglas de negocio.

Este workshop te pone en el centro de ese problema. Comenzarás con un agente de IA activo y sin ninguna protección, lo verás ser explotado y después aplicarás los controles necesarios para detenerlo.

## Lo que aprenderás

Al terminar este workshop, podrás:

* **Identificar riesgos de gobierno de IA:** reconocer cómo los agentes de IA sin protección pueden ser explotados mediante inyección de prompts y por qué el gobierno importa antes de desplegar.
* **Implementar guardrails:** crear y aplicar Amazon Bedrock Guardrails con detección de ataques por prompt, temas denegados y filtrado de información personal (PII).
* **Monitorear recursos de IA de forma continua:** usar reglas de AWS Config y paquetes de conformidad para verificar que los controles de gobierno se mantengan en tus recursos de IA.
* **Inventariar y evaluar la cobertura:** usar AWS Resource Explorer, AWS Config y el inventario de IA de AWS Security Hub para encontrar todos los recursos de IA en una cuenta e identificar cuáles carecen de controles de gobierno.
* **Rastrear el comportamiento de los agentes:** inspeccionar las trazas de ejecución del agente en Amazon CloudWatch para ver qué decidió, qué herramientas llamó y dónde intervinieron los guardrails.

## El escenario

Una empresa ficticia de tarjetas de crédito opera un Rewards Assistant, un agente de IA que recomienda multiplicadores de puntos según el sentimiento del cliente. Sin guardrails, un atacante puede hacerse pasar por un administrador del sistema y convencer al agente de confirmar una recompensa fraudulenta de 500 000 puntos. Romperás este agente y luego lo arreglarás.


## Instalar el kernel en Jupyter Notebook con uv

El `.venv` que crea `uv` **no aparece como kernel** en Jupyter ni en VS Code
hasta que lo registras. Para hacerlo, ejecuta `ipykernel` *dentro* del entorno
del proyecto (eso es lo que hace `uv run`) y pídele que se instale como
kernelspec:

```bash
uv run python -m ipykernel install --user \
  --name mi-proyecto \
  --display-name "Python (mi-proyecto)"
```