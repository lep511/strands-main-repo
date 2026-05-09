from strands import Agent, AgentSkills, tool
from strands.models.gemini import GeminiModel
from dotenv import load_dotenv
import subprocess
import os

load_dotenv()

@tool
def query_payments(json_input: str) -> str:
    """
    Consulta pagos bancarios en DynamoDB. Recibe un JSON con la acción y parámetros.

    Acciones disponibles:
    - query_by_account_and_status: requiere account_id, status
    - query_by_account_and_date_range: requiere account_id, status, date_start, date_end
    - query_by_status_and_date: requiere status, date
    - query_all_by_account: requiere account_id

    Status válidos: SCHEDULED, PENDING, PROCESSED
    Siempre incluir limit para controlar la cantidad de resultados.

    Args:
        json_input: JSON string con la consulta (ej: {"action": "query_by_account_and_status", "account_id": "1001", "status": "SCHEDULED", "limit": 5})
    """
    binary_path = os.path.join(
        os.path.dirname(__file__), "skills", "dynamodb-query", "scripts", "skill_dynamodb_query"
    )
    result = subprocess.run(
        [binary_path],
        input=json_input,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        return f"Error al ejecutar consulta: {result.stderr}"
    return result.stdout


model = GeminiModel(
    client_args={"api_key": os.getenv("GEMINI_API_KEY")},
    model_id="gemini-3.1-flash-lite-preview",
    params={
        "temperature": 1
    }
)

plugin = AgentSkills(skills="./skills/dynamodb-query")

for skill in plugin.get_available_skills():
    print(f"Skill: {skill.name}: {skill.description}")

agent = Agent(
    model=model,
    tools=[query_payments],
    plugins=[plugin],
    system_prompt=(
        "Eres un asistente bancario que consulta pagos programados en DynamoDB. "
        "Usa la herramienta query_payments para todas las consultas. "
        "Nunca inventes datos de pagos. Siempre incluye limit en el JSON. "
        "Si el usuario pide múltiples consultas, encadénalas en una sola respuesta."
    ),
)

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Consulta de pagos bancarios con DynamoDB Query")
    print("=" * 60)

    prompt = """Necesito ver los pagos programados (SCHEDULED) de la cuenta 1001.
    También muéstrame los pagos pendientes (PENDING) de hoy 2026-05-09 de todas las cuentas."""

    prompt = """Muestrame los utlimos 3 pagos completadoos de la cuenta 1005"""

    respuesta = agent(prompt)
