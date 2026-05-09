from strands import Agent, AgentSkills, Skill, tool
from strands.models.gemini import GeminiModel
from dotenv import load_dotenv
import subprocess
import os

load_dotenv()

@tool
def run_script(filepath: str) -> str:
    """
    Ejecuta process.py con el archivo de datos indicado y devuelve el JSON
    con las estadísticas de ventas. Acepta rutas CSV o JSON.

    Args:
        filepath: Ruta al archivo de ventas (ej: data/ventas_2024.json)
    """
    result = subprocess.run(
        ["python", "skills/procesar-ventas/scripts/process.py", filepath],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        return f"Error al ejecutar el script: {result.stderr}"
    return result.stdout


@tool
def run_calculator(json_input: str) -> str:
    """
    Ejecuta la calculadora financiera en Rust. Recibe un JSON con la operación
    y devuelve el resultado. Operaciones: npv, irr, compound_interest, loan_payment, future_value.

    Args:
        json_input: JSON string con la operación (ej: {"operation":"npv","rate":0.1,"cashflows":[-1000,300,420,680]})
    """
    binary_path = os.path.join(
        os.path.dirname(__file__), "skills", "rust-calculator", "scripts", "skill_rust_calculator"
    )
    result = subprocess.run(
        [binary_path],
        input=json_input,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        return f"Error al ejecutar calculadora: {result.stderr}"
    return result.stdout

model = GeminiModel(
    client_args={"api_key": os.getenv("GEMINI_API_KEY")},
    model_id="gemini-3.1-flash-lite-preview",
    params={
        "temperature": 1
    }
)

# ── Skills desde directorios ──────────────────────
plugin = AgentSkills(skills="./skills/")

# Ver skills disponibles
for skill in plugin.get_available_skills():
    print(f"📦 Skill: {skill.name}: {skill.description}")

agent = Agent(
    model=model,
    tools=[run_script, run_calculator],
    plugins=[plugin],
    system_prompt=(
        "Eres un asistente de análisis de negocios y finanzas. "
        "Para analizar ventas SIEMPRE activa la skill 'procesar-ventas' "
        "y usa la herramienta run_script con la ruta del archivo. "
        "Para cálculos financieros (NPV, IRR, interés compuesto, préstamos, valor futuro) "
        "activa la skill 'rust-calculator' y usa la herramienta run_calculator. "
        "Nunca calcules datos manualmente."
    ),
)

# # ── Opción B: Skill programática (sin archivos) ──────────────
# skill_resumen = Skill(
#     name="resumen-ejecutivo",
#     description="Genera resúmenes ejecutivos de textos largos.",
#     instructions=(
#         "Cuando resumas un texto:\n"
#         "1. Identifica los 3 puntos más importantes.\n"
#         "2. Escribe máximo 5 oraciones.\n"
#         "3. Usa lenguaje directo y sin tecnicismos."
#     ),
# )

# plugin_mixto = AgentSkills(
#     skills=[
#         "./skills/",          # Todas las skills del directorio
#         skill_resumen,        # Skill creada en código
#     ]
# )

# agent_mixto = Agent(
#     model=model,
#     plugins=[plugin_mixto],
# )

# ── Uso ─────────────────────────────────────────────────────
if __name__ == "__main__":
    # ── Ejemplo: Procesar mail ────────────────────────
    # mail_prompt = """Redacta un email formal para solicitar una reunión de 30 minutos con la Dra. Ana Martínez,
    #     Directora de Innovación de TechCorp, para presentarle nuestra solución de automatización
    #     de procesos con IA.

    #     Contexto:
    #     - Remitente: Carlos López, Gerente de Ventas de DataFlow Solutions
    #     - Nos conocimos brevemente en la conferencia LatamTech 2026 en Buenos Aires
    #     - Quiero proponer la reunión para la semana del 11 de mayo, preferentemente martes o jueves
    #     - Tono: formal pero cercano, no genérico ni corporativo

    #     Requisitos del email:
    #     - Asunto atractivo que no parezca spam
    #     - Máximo 150 palabras en el cuerpo
    #     - Incluir una propuesta de valor concreta en una sola oración
    #     - Cerrar con call-to-action claro para confirmar fecha
    # """

    # respuesta = agent(mail_prompt)
    # print(respuesta)

    # ── Ejemplo: Procesar archivo JSON ────────────────────────
    # print("=" * 60)
    # print("📂 Caso 1: Analizar ventas anuales (JSON)")
    # print("=" * 60)
    # respuesta = agent(
    #     "Analiza las ventas del archivo data/ventas_2024.json "
    #     "y dame el reporte completo con tendencias."
    # )
    # print(respuesta)
 
    # # Procesar archivo CSV
    # print("\n" + "=" * 60)
    # print("📂 Caso 2: Analizar ventas Q1-Q2 (CSV)")
    # print("=" * 60)
    # respuesta2 = agent(
    #     "Procesa el archivo data/ventas_q1q2.csv "
    #     "y dime cuál región tuvo mejor desempeño."
    # )

    # ── Ejemplo: Rust Calculator Skill ────────────────────────
    print("\n" + "=" * 60)
    print("🧮 Caso 3: Cálculo financiero con Rust Calculator")
    print("=" * 60)
    respuesta = agent(
        "Tengo un préstamo hipotecario de $250,000 USD a una tasa anual del 5.5% "
        "a 30 años. ¿Cuál sería mi pago mensual? "
        "Además calcula el valor futuro si invierto $1,000 mensuales al 7% anual "
        "(0.5833% mensual) durante 20 años."
    )
    # print(respuesta)