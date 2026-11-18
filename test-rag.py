"""Проверка rag.py: русский корпус (docs) и английский (docs_en), включая отказы."""

import json
import os
import subprocess
import sys
from pathlib import Path

ПАПКА = Path(__file__).parent

СЛУЧАИ = [
    ("docs_en", "How much is a boiler service?", "£85"),
    ("docs_en", "Do you require a deposit?", "never ask for a deposit"),
    ("docs_en", "Do you cover Leeds?", "outside our area"),
    ("docs_en", "Can you install a heat pump?", "do not install heat pumps"),
    ("docs_en", "Can I pay by card?", "card"),
    ("docs_en", "How much is a CP12 for two appliances?", "£75"),
    ("docs_en", "How much is a radiator?", "£220"),
    ("docs_en", "Are you Gas Safe registered?", None),
    ("docs_en", "Do you offer finance?", None),
    ("docs_en", "Do you do solar panels?", None),
    ("docs", "Берёте ли предоплату?", "Оплата только после"),
    ("docs", "Работаете ли с юридическими лицами?", "выставляем счёт"),
    ("docs", "Есть ли доставка в Казань?", None),
]


def спросить(корпус: str, вопрос: str) -> dict:
    окружение = dict(os.environ)
    окружение["PYTHONIOENCODING"] = "utf-8"
    вывод = subprocess.run(
        [sys.executable, "rag.py", корпус, вопрос],
        cwd=ПАПКА,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=окружение,
    )
    if вывод.returncode != 0:
        raise RuntimeError(вывод.stderr[-400:])
    return json.loads(вывод.stdout)


провалов = 0
for корпус, вопрос, ожидание in СЛУЧАИ:
    ответ = спросить(корпус, вопрос)
    текст = str(ответ.get("answer", ""))
    if ожидание is None:
        хорошо = "не нашёл" in текст or "couldn't find" in текст
        вердикт = "OK отказ" if хорошо else f"ПРОВАЛ (ответил: {текст[:60]})"
    else:
        хорошо = ожидание.lower() in текст.lower()
        вердикт = "OK" if хорошо else f"ПРОВАЛ (ждём «{ожидание}»: {текст[:60]})"
    if not хорошо:
        провалов += 1
    print(f"{вердикт:30} {корпус:8} {вопрос}")

print(f"\nИТОГ: {len(СЛУЧАИ) - провалов} из {len(СЛУЧАИ)}")
