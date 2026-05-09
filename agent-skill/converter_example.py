from strands import Agent, AgentSkills, tool
from strands.models.gemini import GeminiModel
from dotenv import load_dotenv
import subprocess
import os

load_dotenv()


@tool
def run_converter(json_input: str) -> str:
    """
    Ejecuta el conversor de longitud en Rust. Recibe un JSON con value, from y to,
    y devuelve el resultado. Unidades: meter, kilometer, centimeter, millimeter, mile, yard, foot, inch.

    Args:
        json_input: JSON string con la conversión (ej: {"value": 10, "from": "kilometer", "to": "mile"})
    """
    binary_path = os.path.join(
        os.path.dirname(__file__), "skills", "rust-converter", "scripts", "skill_rust_converter"
    )
    result = subprocess.run(
        [binary_path],
        input=json_input,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        return f"Error al ejecutar conversor: {result.stderr}"
    return result.stdout


model = GeminiModel(
    client_args={"api_key": os.getenv("GEMINI_API_KEY")},
    model_id="gemini-3.1-flash-lite-preview",
    params={
        "temperature": 1
    }
)

plugin = AgentSkills(skills="./skills/rust-converter")

for skill in plugin.get_available_skills():
    print(f"📦 Skill: {skill.name}: {skill.description}")

agent = Agent(
    model=model,
    tools=[run_converter],
    plugins=[plugin],
    system_prompt=(
        "Eres un asistente de conversión de unidades de longitud. "
        "Para convertir unidades SIEMPRE activa la skill 'rust-converter' "
        "y usa la herramienta run_converter. "
        "Nunca calcules conversiones manualmente."
    ),
)

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("📏 Conversión de unidades de longitud con Rust Converter")
    print("=" * 60)
    respuesta = agent(
        "Mido 5 pies con 11 pulgadas. ¿Cuánto es eso en metros y centímetros? "
        "También dime cuántos kilómetros son 26.2 millas (un maratón)."
    )
