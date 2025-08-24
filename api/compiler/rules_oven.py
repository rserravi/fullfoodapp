from typing import List
from ..schemas import StepGeneric, AppliancePlanStep
DEFAULTS = {"preheat_c": 220, "cook_c": 200}

def compile_steps(steps: List[StepGeneric]) -> List[AppliancePlanStep]:
    plan: List[AppliancePlanStep] = []
    if any(s.action == "cook" for s in steps):
        plan.append(AppliancePlanStep(action="preheat", temperature_c=DEFAULTS["preheat_c"], time_min=10,
                                      instructions="Precalienta el horno a 220°C (10 min)."))
    for s in steps:
        if s.action == "cook":
            t = s.temperature_c or DEFAULTS["cook_c"]
            time = s.time_min or 20
            plan.append(AppliancePlanStep(action="cook", temperature_c=t, time_min=time,
                                          instructions=f"Hornea a {t}°C durante {time} min."))
        elif s.action in ("prep","season"):
            plan.append(AppliancePlanStep(action=s.action, temperature_c=None, time_min=s.time_min,
                                          instructions=s.description))
        elif s.action == "flip":
            plan.append(AppliancePlanStep(action="flip", temperature_c=None, time_min=None,
                                          instructions="Gira la bandeja o voltea; continúa la cocción."))
        elif s.action == "rest":
            plan.append(AppliancePlanStep(action="rest", temperature_c=None, time_min=s.time_min or 3,
                                          instructions="Deja reposar fuera del horno."))
        elif s.action == "serve":
            plan.append(AppliancePlanStep(action="serve", temperature_c=None, time_min=None,
                                          instructions="Emplata y sirve."))
    return plan
