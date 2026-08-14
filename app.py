from __future__ import annotations

import base64
import csv
import hmac
import hashlib
import json
import io
import re
import os
import sys
import unicodedata
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from functools import wraps
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
CAPACITACIONES_PATH = DATA_DIR / "capacitaciones.csv"
USUARIOS_PATH = DATA_DIR / "usuarios.csv"

ALUMNOS_DATA_DIR = DATA_DIR / "alumnos"
ALUMNOS_CAPACITACIONES_PATH = ALUMNOS_DATA_DIR / "capacitaciones.csv"
ALUMNOS_USUARIOS_PATH = ALUMNOS_DATA_DIR / "usuarios.csv"
ALUMNOS_PENDIENTES_PATH = ALUMNOS_DATA_DIR / "pendientes_revision.csv"
ALUMNOS_DESCARTADOS_PATH = ALUMNOS_DATA_DIR / "descartados_menos_30_min.csv"
ALUMNOS_INSUMOS_DIR = ALUMNOS_DATA_DIR / "insumos_meet"
ALUMNOS_MEET_PROCESADOS_PATH = ALUMNOS_DATA_DIR / "meet_descargados.csv"

MAESTROS_DATA_DIR = DATA_DIR / "maestros"
MAESTROS_INSUMOS_MEET_DIR = MAESTROS_DATA_DIR / "insumos_meet"
MAESTROS_HORARIOS_PATH = MAESTROS_DATA_DIR / "horarios_cursos.csv"
MAESTROS_PENDIENTES_MEET_PATH = MAESTROS_DATA_DIR / "pendientes_revision_meet.csv"
MAESTROS_DESCARTADOS_MEET_PATH = MAESTROS_DATA_DIR / "descartados_menos_30_min_meet.csv"

MEET_API_MOVE_PROCESSED_FILES = os.getenv("MEET_API_MOVE_PROCESSED_FILES", "1").strip().lower() in {"1", "true", "yes", "si", "sí"}
READ_REPORTS_FROM_DB = os.getenv("READ_REPORTS_FROM_DB", "1").strip().lower() in {"1", "true", "yes", "si", "sí"}
REPORT_CACHE_ENABLED = os.getenv("REPORT_CACHE_ENABLED", "1").strip().lower() in {"1", "true", "yes", "si", "sí"}
REPORT_CACHE_DIR = DATA_DIR / "cache"
MAESTROS_REPORT_CACHE_PATH = REPORT_CACHE_DIR / "reporte_maestros.json"
ALUMNOS_REPORT_CACHE_PATH = REPORT_CACHE_DIR / "reporte_alumnos.json"
REPORT_UPDATE_TIMESTAMPS_PATH = REPORT_CACHE_DIR / "ultimas_actualizaciones_reportes.json"

MEET_API_TOKEN = os.getenv("MEET_API_TOKEN", "").strip()
MEET_API_DIRECT_ENABLED = os.getenv("MEET_API_DIRECT_ENABLED", "1").strip().lower() in {"1", "true", "yes", "si", "sí"}
MEET_API_ALLOW_TOKEN_IN_BODY = os.getenv("MEET_API_ALLOW_TOKEN_IN_BODY", "1").strip().lower() in {"1", "true", "yes", "si", "sí"}
PUBLIC_APP_URL = os.getenv("PUBLIC_APP_URL", "").strip().rstrip("/")
AUTO_REGENERAR_CACHE_REMOTO = os.getenv("AUTO_REGENERAR_CACHE_REMOTO", "0").strip().lower() in {"1", "true", "yes", "si", "sí"}
REMOTE_CACHE_TOKEN = (
    os.getenv("REMOTE_CACHE_TOKEN", "").strip()
    or os.getenv("CACHE_API_TOKEN", "").strip()
    or MEET_API_TOKEN
)
try:
    REMOTE_CACHE_TIMEOUT = float(os.getenv("REMOTE_CACHE_TIMEOUT", "30"))
except ValueError:
    REMOTE_CACHE_TIMEOUT = 30.0

CAPACITACIONES_API_TOKEN = (
    os.getenv("CAPACITACIONES_API_TOKEN", "").strip()
    or os.getenv("MAESTROS_CAPACITACIONES_API_TOKEN", "").strip()
    or MEET_API_TOKEN
)
CAPACITACIONES_API_ENABLED = os.getenv("CAPACITACIONES_API_ENABLED", "1").strip().lower() in {"1", "true", "yes", "si", "sí"}
CAPACITACIONES_API_ORIGEN = os.getenv("CAPACITACIONES_API_ORIGEN", "api_capacitaciones_en_linea").strip() or "api_capacitaciones_en_linea"
CAPACITACIONES_API_MODALIDAD = os.getenv("CAPACITACIONES_API_MODALIDAD", "En línea").strip() or "En línea"

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
REPORT_PASSWORD = os.getenv("REPORT_PASSWORD")

if not ADMIN_PASSWORD:
    raise RuntimeError("Falta definir ADMIN_PASSWORD en el archivo .env")

if not REPORT_PASSWORD:
    raise RuntimeError("Falta definir REPORT_PASSWORD en el archivo .env")

ALLOWED_EXTENSIONS = {"csv"}

CURSOS_OFICIALES = [
    "CANVAS 1. INTRODUCCIÓN Y APUNTES.",
    "CANVAS 2. TAREAS Y SPEEDGRADER.",
    "CANVAS 3. GRUPOS (EQUIPOS).",
    "CANVAS 4. RÚBRICAS.",
    "CANVAS 5. FOROS DE DISCUSIÓN.",
    "CANVAS 6. EXÁMENES Y SPEEDGRADER.",
    "CANVAS 7. INDUCCIÓN PARA DOCENTES (MATERIA EN LÍNEA).",
]

MODALIDADES_OFICIALES = [
    "Presencial",
    "En línea",
    "A distancia",
]

MODALIDADES = MODALIDADES_OFICIALES

ALUMNOS_CURSO_OFICIAL = os.getenv("ALUMNOS_CURSO_OFICIAL", "CURSO DE ALUMNOS")
ALUMNOS_CURSOS_OFICIALES = [ALUMNOS_CURSO_OFICIAL]
ALUMNOS_MODALIDAD_REVALIDACION = os.getenv("ALUMNOS_MODALIDAD_REVALIDACION", "Revalidado")
ALUMNOS_REVALIDACION_ORIGEN = os.getenv("ALUMNOS_REVALIDACION_ORIGEN", "revalidacion_inicial")
ALUMNOS_REVALIDACION_OBSERVACION = os.getenv("ALUMNOS_REVALIDACION_OBSERVACION", "Alumno con materia previa en Canvas")
ALUMNOS_MODALIDADES = list(dict.fromkeys(["A distancia", ALUMNOS_MODALIDAD_REVALIDACION]))
ALUMNOS_MINUTOS_MINIMOS = int(os.getenv("ALUMNOS_MINUTOS_MINIMOS", "30"))
MAESTROS_MINUTOS_MINIMOS = int(os.getenv("MAESTROS_MINUTOS_MINIMOS", "30"))
MAESTROS_HORARIOS_TOLERANCIA_MINUTOS = int(os.getenv("MAESTROS_HORARIOS_TOLERANCIA_MINUTOS", "15"))


class MeetAutomationError(RuntimeError):
    pass


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cambia-esta-clave-en-produccion")
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def report_login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if session.get("report_logged_in"):
            return view(*args, **kwargs)

        session["next_url"] = request.full_path if request.query_string else request.path
        return redirect(url_for("login"))

    return wrapped_view


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin"))
        return view(*args, **kwargs)

    return wrapped_view


def template_context() -> dict[str, Any]:
    return {
        "report_logged_in": session.get("report_logged_in", False),
    }


def repair_mojibake(value: Any) -> str:
    text = str(value or "")

    if not any(marker in text for marker in ("Ã", "Â", "â")):
        return text

    for encoding in ("cp1252", "latin1"):
        try:
            repaired = text.encode(encoding).decode("utf-8")
            if repaired and repaired != text:
                return repaired
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue

    return text


def clean(value: Any) -> str:
    text = repair_mojibake(value).strip()
    if text.lower() in {"null", "none", "nan", "n/a", "na", "sin dato", "sin datos"}:
        return ""
    return text


def norm(value: Any) -> str:
    text = clean(value).lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return " ".join(text.split())


def normalize_email(value: Any) -> str:
    return clean(value).lower()


def correct_future_swapped_date(fecha: datetime) -> datetime:
    if not fecha or fecha == datetime.min:
        return fecha

    hoy = mexico_now().replace(tzinfo=None)
    limite_futuro = hoy + timedelta(days=7)

    if (
        fecha.year == hoy.year
        and fecha.date() > limite_futuro.date()
        and 1 <= fecha.day <= 12
        and 1 <= fecha.month <= 12
    ):
        try:
            invertida = datetime(fecha.year, fecha.day, fecha.month)
        except ValueError:
            return fecha

        if invertida.date() <= limite_futuro.date():
            return invertida

    return fecha


def parse_training_date_value(value: Any) -> datetime | None:
    text = clean(value)
    if not text:
        return None

    date_text = text.split()[0]

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%m/%d/%Y", "%m-%d-%Y"):
        try:
            return correct_future_swapped_date(datetime.strptime(date_text, fmt))
        except ValueError:
            continue

    return None


def parse_date(value: str) -> datetime:
    return parse_training_date_value(value) or datetime.min


def mexico_now() -> datetime:
    return datetime.now(ZoneInfo("America/Mexico_City"))


def mexico_now_label() -> str:
    return mexico_now().strftime("%d/%m/%Y %H:%M")


def parse_datetime_flexible(value: Any) -> datetime:
    text = clean(value)
    if not text:
        return datetime.min

    for fmt in (
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d",
        "%d/%m/%Y",
    ):
        try:
            return datetime.strptime(text[:19], fmt) if "T" in fmt and len(text) > 19 else datetime.strptime(text, fmt)
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return datetime.min

def get_last_update_label(path: Path = CAPACITACIONES_PATH) -> str:
    if path.exists():
        mexico_tz = ZoneInfo("America/Mexico_City")
        modified_utc = datetime.fromtimestamp(
            path.stat().st_mtime,
            tz=timezone.utc,
        )
        modified_mexico = modified_utc.astimezone(mexico_tz)
        return modified_mexico.strftime("%d/%m/%Y %H:%M")

    return "Sin datos"


def get_value(row: dict[str, str], *keys: str) -> str:
    normalized = {norm(key): value for key, value in row.items()}
    for key in keys:
        if norm(key) in normalized:
            return clean(normalized[norm(key)])
    return ""


def is_truthy_marker(value: Any) -> bool:
    value_norm = norm(value)
    return value_norm in {
        "1",
        "true",
        "yes",
        "si",
        "sí",
        "x",
        "ml",
        "materia en linea",
        "materia en línea",
        "en linea",
        "en línea",
        "online",
    }


def user_has_materia_linea(user: dict[str, Any] | None) -> bool:
    if not user:
        return False
    return is_truthy_marker(
        user.get("ml")
        or user.get("ML")
        or user.get("materia_linea")
        or user.get("materia_en_linea")
    )


def normalize_user_row(row: dict[str, str]) -> dict[str, str]:
    ml = get_value(row, "ml", "ML", "materia_linea", "materia en linea", "materia en línea", "materia_en_linea")
    return {
        "id": get_value(row, "id", "ID", "matricula", "matrícula", "numero", "número"),
        "nombre": get_value(row, "nombre", "Nombre", "name", "participante"),
        "correo": get_value(row, "correo", "Correo", "correo electronico", "correo electrónico", "Correo electrónico", "email", "mail", "e-mail"),
        "carrera": get_value(row, "carrera", "Carrera", "licenciatura", "Licenciatura", "programa", "Programa"),
        "division": get_value(row, "division", "División", "Division", "dirección", "Direccion", "area", "Área"),
        "ml": "1" if is_truthy_marker(ml) else "0",
        "materia_linea": is_truthy_marker(ml),
    }


def normalize_training_row(row: dict[str, str]) -> dict[str, str]:
    return {
        "id": get_value(row, "id", "ID", "matricula", "matrícula", "numero", "número"),
        "nombre": get_value(row, "nombre", "Nombre", "name", "participante"),
        "correo": get_value(row, "correo", "Correo", "correo electronico", "correo electrónico", "Correo electrónico", "email", "mail", "e-mail"),
        "carrera": get_value(row, "carrera", "Carrera", "licenciatura", "Licenciatura", "programa", "Programa"),
        "division": get_value(row, "division", "División", "Division", "dirección", "Direccion", "area", "Área"),
        "curso": get_value(row, "curso", "Curso"),
        "modalidad": get_value(row, "modalidad", "Modalidad"),
        "fecha_actualizacion": get_value(row, "fecha_actualizacion", "Fecha_actualizacion", "fecha", "Fecha", "actualizacion", "actualización"),
        "origen": get_value(row, "origen", "Origen", "fuente", "Fuente"),
        "observacion": get_value(row, "observacion", "observación", "Observacion", "Observación", "comentario", "Comentario"),
    }


def normalize_meet_row(row: dict[str, str]) -> dict[str, str]:
    nombre = get_value(row, "nombre", "Nombre", "name", "first name", "primer nombre")
    apellido = get_value(row, "apellido", "Apellido", "apellidos", "Apellidos", "last name")
    nombre_completo = " ".join(part for part in [nombre, apellido] if part).strip()

    return {
        "nombre": nombre_completo or get_value(row, "nombre completo", "Nombre completo", "participante", "usuario"),
        "correo": get_value(
            row,
            "correo electronico", "Correo electronico", "correo electrónico", "Correo electrónico",
            "email", "mail", "correo", "Correo",
        ),
        "duracion": get_value(
            row,
            "duracion", "Duración", "duracion total", "Duración total",
            "duracion total minutos", "Duración total minutos", "duration", "duration minutes",
        ),
        "hora_unio": get_value(
            row,
            "hora a la que se unio", "Hora a la que se unió", "hora a la que se unió",
            "hora de entrada", "hora entrada", "join time", "joined", "time joined",
        ),
        "hora_salio": get_value(
            row,
            "hora a la que salio", "Hora a la que salió", "hora a la que se salió",
            "hora de salida", "hora salida", "leave time", "left", "time left",
        ),
        "fecha_actualizacion": get_value(row, "fecha_actualizacion", "fecha", "Fecha", "date"),
    }


def parse_duration_minutes(value: Any) -> float | None:
    text = clean(value).lower().replace(",", ".")

    if not text:
        return None

    if ":" in text:
        parts = [part.strip() for part in text.split(":")]
        try:
            numbers = [float(part) for part in parts]
        except ValueError:
            return None

        if len(numbers) == 3:
            hours, minutes, seconds = numbers
            return hours * 60 + minutes + seconds / 60

        if len(numbers) == 2:
            minutes, seconds = numbers
            return minutes + seconds / 60

    hours = 0.0
    minutes = 0.0
    seconds = 0.0

    hour_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:h|hr|hrs|hora|horas)\b", text)
    minute_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:m|min|mins|minuto|minutos)\b", text)
    second_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:s|seg|segs|segundo|segundos)\b", text)

    if hour_match:
        hours = float(hour_match.group(1))

    if minute_match:
        minutes = float(minute_match.group(1))

    if second_match:
        seconds = float(second_match.group(1))

    if hour_match or minute_match or second_match:
        return hours * 60 + minutes + seconds / 60

    number_match = re.search(r"\d+(?:\.\d+)?", text)
    if number_match:
        return float(number_match.group(0))

    return None


def format_date_label(value: Any = "") -> str:
    value = clean(value)

    if not value:
        return mexico_now().strftime("%d/%m/%Y")

    fecha = parse_training_date_value(value)
    if fecha:
        return fecha.strftime("%d/%m/%Y")

    return value


def write_csv(path: Path, rows: list[dict[str, Any]], headers: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({header: row.get(header, "") for header in headers})


def deduplicate_training_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: dict[tuple[str, str, str, str], dict[str, str]] = {}

    for row in rows:
        persona_key = row.get("id") or normalize_email(row.get("correo")) or norm(row.get("nombre"))
        key = (persona_key, norm(row.get("curso")), norm(row.get("modalidad")), normalize_email(row.get("correo")))
        previous = deduped.get(key)

        if not previous or parse_date(row.get("fecha_actualizacion", "")) >= parse_date(previous.get("fecha_actualizacion", "")):
            deduped[key] = row

    return sorted(deduped.values(), key=lambda item: parse_date(item.get("fecha_actualizacion", "")), reverse=True)


def read_processed_meet_records() -> set[tuple[str, str]]:
    if not ALUMNOS_MEET_PROCESADOS_PATH.exists():
        return set()

    records: set[tuple[str, str]] = set()
    with ALUMNOS_MEET_PROCESADOS_PATH.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            message_id = clean(row.get("mensaje_id"))
            resource_id = clean(row.get("recurso_id"))
            if message_id and resource_id:
                records.add((message_id, resource_id))
    return records


def append_processed_meet_records(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return

    headers = [
        "mensaje_id",
        "recurso_id",
        "archivo",
        "origen",
        "asunto",
        "fecha_reunion",
        "fecha_descarga",
        "estado",
        "tipo",
        "detalle",
    ]

    ALUMNOS_MEET_PROCESADOS_PATH.parent.mkdir(parents=True, exist_ok=True)
    exists = ALUMNOS_MEET_PROCESADOS_PATH.exists() and ALUMNOS_MEET_PROCESADOS_PATH.stat().st_size > 0

    with ALUMNOS_MEET_PROCESADOS_PATH.open("a", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow({header: row.get(header, "") for header in headers})










def parse_meet_subject_date(subject: str, fallback_timestamp_ms: str | None = None) -> str:
    subject = repair_mojibake(subject)
    month_map = {
        "ene": 1, "enero": 1,
        "feb": 2, "febrero": 2,
        "mar": 3, "marzo": 3,
        "abr": 4, "abril": 4,
        "may": 5, "mayo": 5,
        "jun": 6, "junio": 6,
        "jul": 7, "julio": 7,
        "ago": 8, "agosto": 8,
        "sep": 9, "sept": 9, "septiembre": 9,
        "oct": 10, "octubre": 10,
        "nov": 11, "noviembre": 11,
        "dic": 12, "diciembre": 12,
    }

    match = re.search(
        r"(\d{1,2})\s+([a-záéíóúñ]{3,12})\s+(\d{4})",
        subject,
        flags=re.IGNORECASE,
    )

    if match:
        day = int(match.group(1))
        month_text = norm(match.group(2))
        year = int(match.group(3))
        month = month_map.get(month_text)
        if month:
            return datetime(year, month, day).strftime("%d/%m/%Y")

    if fallback_timestamp_ms:
        try:
            mexico_tz = ZoneInfo("America/Mexico_City")
            timestamp = int(fallback_timestamp_ms) / 1000
            return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(mexico_tz).strftime("%d/%m/%Y")
        except (TypeError, ValueError):
            pass

    return format_date_label()



def parse_time_value(value: Any) -> tuple[int, int] | None:
    text = clean(value).lower()

    if not text:
        return None

    text = text.replace(".", " ").replace("_", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace("p m", "pm").replace("a m", "am")

    match = re.search(r"(\d{1,2})\s*[: ]\s*(\d{2})\s*(am|pm)?", text, flags=re.IGNORECASE)
    if not match:
        match = re.search(r"^(\d{1,2})\s*(am|pm)$", text, flags=re.IGNORECASE)
        if not match:
            return None
        hour = int(match.group(1))
        minute = 0
        meridian = match.group(2)
    else:
        hour = int(match.group(1))
        minute = int(match.group(2))
        meridian = match.group(3)

    if meridian:
        meridian = meridian.lower()
        if meridian == "pm" and hour < 12:
            hour += 12
        if meridian == "am" and hour == 12:
            hour = 0

    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return hour, minute

    return None


def parse_meet_subject_datetime(subject: str, fallback_timestamp_ms: str | None = None) -> datetime | None:
    subject = repair_mojibake(subject)
    normalized_subject = subject.replace("_", " ").replace("-", " ")
    month_map = {
        "ene": 1, "enero": 1,
        "feb": 2, "febrero": 2,
        "mar": 3, "marzo": 3,
        "abr": 4, "abril": 4,
        "may": 5, "mayo": 5,
        "jun": 6, "junio": 6,
        "jul": 7, "julio": 7,
        "ago": 8, "agosto": 8,
        "sep": 9, "sept": 9, "septiembre": 9,
        "oct": 10, "octubre": 10,
        "nov": 11, "noviembre": 11,
        "dic": 12, "diciembre": 12,
    }

    match = re.search(
        r"(\d{1,2})\s+([a-záéíóúñ]{3,12})\s+(\d{4})(?:.*?(\d{1,2})\s*[: ]\s*(\d{2})\s*(am|pm)?)?",
        normalized_subject,
        flags=re.IGNORECASE,
    )

    if match:
        day = int(match.group(1))
        month_text = norm(match.group(2))
        year = int(match.group(3))
        month = month_map.get(month_text)
        if month:
            hour = int(match.group(4) or 0)
            minute = int(match.group(5) or 0)
            meridian = (match.group(6) or "").lower()
            if meridian == "pm" and hour < 12:
                hour += 12
            if meridian == "am" and hour == 12:
                hour = 0
            return datetime(year, month, day, hour, minute)

    if fallback_timestamp_ms:
        try:
            mexico_tz = ZoneInfo("America/Mexico_City")
            timestamp = int(fallback_timestamp_ms) / 1000
            return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(mexico_tz).replace(tzinfo=None)
        except (TypeError, ValueError):
            pass

    return None


def parse_date_value(value: Any) -> datetime | None:
    return parse_training_date_value(value)


def canonicalize_maestro_course(value: Any) -> str:
    text = clean(value)
    text_norm = norm(text)

    if not text_norm:
        return ""

    for official in CURSOS_OFICIALES:
        if norm(official) == text_norm:
            return official

    for index, official in enumerate(CURSOS_OFICIALES, start=1):
        if f"canvas {index}" in text_norm or f"canvas{index}" in text_norm or f"curso {index}" in text_norm:
            return official

    if "induccion" in text_norm and ("docente" in text_norm or "materia en linea" in text_norm):
        return CURSOS_OFICIALES[6]
    if "introduccion" in text_norm or "apuntes" in text_norm:
        return CURSOS_OFICIALES[0]
    if "tareas" in text_norm and "speedgrader" in text_norm:
        return CURSOS_OFICIALES[1]
    if "grupos" in text_norm or "equipos" in text_norm:
        return CURSOS_OFICIALES[2]
    if "rubrica" in text_norm or "rubricas" in text_norm:
        return CURSOS_OFICIALES[3]
    if "foro" in text_norm or "foros" in text_norm or "discusion" in text_norm:
        return CURSOS_OFICIALES[4]
    if "examen" in text_norm or "examenes" in text_norm:
        return CURSOS_OFICIALES[5]

    return text


def read_maestros_horarios() -> list[dict[str, Any]]:
    if not MAESTROS_HORARIOS_PATH.exists():
        return []

    horarios: list[dict[str, Any]] = []
    with MAESTROS_HORARIOS_PATH.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            curso = canonicalize_maestro_course(get_value(row, "curso", "Curso"))
            modalidad = get_value(row, "modalidad", "Modalidad") or "A distancia"
            fecha_raw = get_value(row, "fecha", "Fecha")
            hora_inicio_raw = get_value(row, "hora_inicio", "hora inicio", "Hora inicio", "inicio")
            hora_fin_raw = get_value(row, "hora_fin", "hora fin", "Hora fin", "fin")
            fecha_dt = parse_date_value(fecha_raw)
            hora_inicio = parse_time_value(hora_inicio_raw)
            hora_fin = parse_time_value(hora_fin_raw)

            if not curso or not fecha_dt or not hora_inicio or not hora_fin:
                continue

            inicio_minutos = hora_inicio[0] * 60 + hora_inicio[1]
            fin_minutos = hora_fin[0] * 60 + hora_fin[1]

            horarios.append({
                "curso": curso,
                "modalidad": normalizar_modalidad_simple(modalidad),
                "fecha": fecha_dt.date(),
                "fecha_label": fecha_dt.strftime("%d/%m/%Y"),
                "hora_inicio": hora_inicio_raw,
                "hora_fin": hora_fin_raw,
                "inicio_minutos": inicio_minutos,
                "fin_minutos": fin_minutos,
            })

    return horarios


def normalizar_modalidad_simple(value: Any) -> str:
    text_norm = norm(value)
    if "presencial" in text_norm:
        return "Presencial"
    if "linea" in text_norm or "online" in text_norm or "virtual" in text_norm:
        return "En línea"
    if "distancia" in text_norm or "zoom" in text_norm or "meet" in text_norm or "remoto" in text_norm:
        return "A distancia"
    return clean(value) or "A distancia"


def buscar_horario_maestro(
    horarios: list[dict[str, Any]],
    fecha_reunion: datetime | None,
    hora_participante: str = "",
) -> dict[str, Any] | None:
    if not horarios or not fecha_reunion:
        return None

    fecha = fecha_reunion.date()
    hora = parse_time_value(hora_participante)
    minutos = None

    if hora:
        minutos = hora[0] * 60 + hora[1]
    elif fecha_reunion.hour or fecha_reunion.minute:
        minutos = fecha_reunion.hour * 60 + fecha_reunion.minute

    candidatos_fecha = [horario for horario in horarios if horario["fecha"] == fecha]

    if not candidatos_fecha:
        return None

    if minutos is None:
        return candidatos_fecha[0] if len(candidatos_fecha) == 1 else None

    tolerancia = MAESTROS_HORARIOS_TOLERANCIA_MINUTOS
    candidatos_hora = [
        horario
        for horario in candidatos_fecha
        if (horario["inicio_minutos"] - tolerancia) <= minutos <= (horario["fin_minutos"] + tolerancia)
    ]

    if candidatos_hora:
        return sorted(
            candidatos_hora,
            key=lambda horario: abs(minutos - horario["inicio_minutos"]),
        )[0]

    return None

def safe_download_filename(prefix: str, original_name: str) -> str:
    original_name = original_name or "asistencia_meet.csv"
    if not original_name.lower().endswith(".csv"):
        original_name = f"{Path(original_name).stem}.csv"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return secure_filename(f"{timestamp}_{prefix}_{original_name}")


def clasificar_meet_por_asunto(subject: str) -> str:
    subject_norm = norm(subject)

    if "meet maestros" in subject_norm:
        return "maestros"

    if "meet alumnos" in subject_norm:
        return "alumnos"

    return "alumnos"


def get_meet_target_dir(tipo: str) -> Path:
    if tipo == "maestros":
        return MAESTROS_INSUMOS_MEET_DIR

    return ALUMNOS_INSUMOS_DIR


def get_meet_target_prefix(tipo: str) -> str:
    return "meet_maestros" if tipo == "maestros" else "meet_alumnos"


def normalize_meet_tipo(value: Any, subject: str = "") -> str:
    text_norm = norm(value)

    if text_norm in {"maestro", "maestros", "docente", "docentes"}:
        return "maestros"

    if text_norm in {"alumno", "alumnos", "estudiante", "estudiantes"}:
        return "alumnos"

    return clasificar_meet_por_asunto(subject)


def get_meet_api_token_from_request() -> str:
    auth = clean(request.headers.get("Authorization", ""))
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()

    for header_name in ("X-Meet-Api-Token", "X-Meet-Token", "X-Api-Token"):
        value = clean(request.headers.get(header_name, ""))
        if value:
            return value

    if MEET_API_ALLOW_TOKEN_IN_BODY:
        if request.is_json:
            data = request.get_json(silent=True) or {}
            value = clean(data.get("token", ""))
            if value:
                return value

        value = clean(request.form.get("token", ""))
        if value:
            return value

    return ""


def validate_meet_api_token() -> tuple[bool, str]:
    if not MEET_API_DIRECT_ENABLED:
        return False, "La API directa de Meet está deshabilitada."

    if not MEET_API_TOKEN:
        return False, "Falta configurar MEET_API_TOKEN en variables de entorno."

    supplied = get_meet_api_token_from_request()
    if not supplied or not hmac.compare_digest(supplied, MEET_API_TOKEN):
        return False, "Token no autorizado."

    return True, ""



def get_capacitaciones_api_token_from_request() -> str:
    auth = clean(request.headers.get("Authorization", ""))
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()

    for header_name in ("X-Capacitaciones-Api-Token", "X-Maestros-Api-Token", "X-Api-Token", "X-Meet-Api-Token"):
        value = clean(request.headers.get(header_name, ""))
        if value:
            return value

    if request.is_json:
        data = request.get_json(silent=True) or {}
        value = clean(data.get("token", ""))
        if value:
            return value

    value = clean(request.form.get("token", ""))
    if value:
        return value

    return ""


def validate_capacitaciones_api_token() -> tuple[bool, str]:
    if not CAPACITACIONES_API_ENABLED:
        return False, "La API de capacitaciones está deshabilitada."

    if not CAPACITACIONES_API_TOKEN:
        return False, "Falta configurar CAPACITACIONES_API_TOKEN o MEET_API_TOKEN en variables de entorno."

    supplied = get_capacitaciones_api_token_from_request()
    if not supplied or not hmac.compare_digest(supplied, CAPACITACIONES_API_TOKEN):
        return False, "Token no autorizado."

    return True, ""


def decode_csv_bytes(content: bytes) -> str:
    if not content:
        return ""

    ultimo_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError as exc:
            ultimo_error = exc
            continue

    if ultimo_error:
        raise ultimo_error

    return content.decode("utf-8", errors="replace")


def csv_text_to_rows(csv_text: str) -> list[dict[str, str]]:
    if not clean(csv_text):
        return []

    reader = csv.DictReader(io.StringIO(csv_text))
    return [{str(k or ""): clean(v) for k, v in row.items()} for row in reader]


def read_capacitaciones_import_payload() -> tuple[dict[str, str], list[dict[str, Any]], bytes]:
    metadata: dict[str, str] = {}
    rows: list[dict[str, Any]] = []
    content: bytes = b""

    if request.is_json:
        data = request.get_json(silent=True) or {}
        metadata = {
            "filename": clean(data.get("filename", data.get("archivo", "capacitaciones_maestros_en_linea.csv"))),
            "origen": clean(data.get("origen", "")) or CAPACITACIONES_API_ORIGEN,
            "asunto": clean(data.get("subject", data.get("asunto", ""))),
            "ingesta_id": clean(data.get("ingesta_id", data.get("message_id", data.get("mensaje_id", "")))),
            "fecha_actualizacion": clean(data.get("fecha_actualizacion", data.get("fecha", ""))),
        }

        registros = data.get("registros")
        if isinstance(registros, list):
            rows = [dict(registro) for registro in registros if isinstance(registro, dict)]
            content = json.dumps(rows, ensure_ascii=False, sort_keys=True).encode("utf-8")
            return metadata, rows, content

        csv_base64 = clean(data.get("csv_base64", ""))
        if csv_base64:
            padded = csv_base64 + "=" * (-len(csv_base64) % 4)
            content = base64.b64decode(padded.encode("utf-8"))
        else:
            csv_text = data.get("csv", data.get("csv_text", ""))
            content = str(csv_text or "").encode("utf-8-sig")

        rows = csv_text_to_rows(decode_csv_bytes(content))
        return metadata, rows, content

    metadata = {
        "filename": clean(request.form.get("filename", request.form.get("archivo", "capacitaciones_maestros_en_linea.csv"))),
        "origen": clean(request.form.get("origen", "")) or CAPACITACIONES_API_ORIGEN,
        "asunto": clean(request.form.get("subject", request.form.get("asunto", ""))),
        "ingesta_id": clean(request.form.get("ingesta_id", request.form.get("message_id", request.form.get("mensaje_id", "")))),
        "fecha_actualizacion": clean(request.form.get("fecha_actualizacion", request.form.get("fecha", ""))),
    }

    uploaded_file = request.files.get("archivo") or request.files.get("file") or request.files.get("csv")
    if uploaded_file and uploaded_file.filename:
        metadata["filename"] = metadata["filename"] or uploaded_file.filename
        content = uploaded_file.read()
    else:
        csv_base64 = clean(request.form.get("csv_base64", ""))
        if csv_base64:
            padded = csv_base64 + "=" * (-len(csv_base64) % 4)
            content = base64.b64decode(padded.encode("utf-8"))
        else:
            content = str(request.form.get("csv", request.form.get("csv_text", "")) or "").encode("utf-8-sig")

    rows = csv_text_to_rows(decode_csv_bytes(content))
    return metadata, rows, content


def normalizar_modalidad_capacitacion_maestro(value: Any) -> str:
    texto_norm = norm(value)
    if not texto_norm:
        return CAPACITACIONES_API_MODALIDAD

    if texto_norm in {"en linea", "online", "virtual", "linea"}:
        return "En línea"
    if texto_norm in {"a distancia", "distancia", "meet", "zoom"}:
        return "A distancia"
    if texto_norm in {"presencial", "presencialmente"}:
        return "Presencial"

    return clean(value) or CAPACITACIONES_API_MODALIDAD


def normalizar_curso_capacitacion_maestro(value: Any) -> str:
    curso = clean(value)
    if not curso:
        return ""

    mapa = {norm(nombre): nombre for nombre in CURSOS_OFICIALES}
    mapa[norm("CANVAS 5. FOROS DE DISCUSIÓN Y SPEEDGRADER.")] = "CANVAS 5. FOROS DE DISCUSIÓN."
    mapa[norm("CANVAS 7. INDUCCIÓN PARA DOCENTES (MATERIA EN LÍNEA)")] = "CANVAS 7. INDUCCIÓN PARA DOCENTES (MATERIA EN LÍNEA)."
    mapa[norm("CANVAS 7. INDUCCION PARA DOCENTES (MATERIA EN LINEA)")] = "CANVAS 7. INDUCCIÓN PARA DOCENTES (MATERIA EN LÍNEA)."
    mapa[norm("INDUCCIÓN PARA DOCENTES (MATERIA EN LÍNEA).")] = "CANVAS 7. INDUCCIÓN PARA DOCENTES (MATERIA EN LÍNEA)."
    mapa[norm("INDUCCION PARA DOCENTES (MATERIA EN LINEA)")] = "CANVAS 7. INDUCCIÓN PARA DOCENTES (MATERIA EN LÍNEA)."

    curso_norm = norm(curso)
    if "induccion" in curso_norm and ("docente" in curso_norm or "materia en linea" in curso_norm):
        return "CANVAS 7. INDUCCIÓN PARA DOCENTES (MATERIA EN LÍNEA)."

    return mapa.get(curso_norm, curso)


def curso_maestro_es_oficial(curso: str) -> bool:
    oficiales = {norm(nombre) for nombre in CURSOS_OFICIALES}
    return norm(curso) in oficiales


def preparar_registros_capacitaciones_maestros(rows: list[dict[str, Any]], metadata: dict[str, str]) -> dict[str, Any]:
    usuarios = read_report_users("maestro")
    by_id, by_email, by_name = build_user_indexes(users=usuarios)

    validos: list[dict[str, str]] = []
    pendientes: list[dict[str, Any]] = []
    errores: list[dict[str, Any]] = []

    fecha_default = format_date_label(metadata.get("fecha_actualizacion") or "") or mexico_now().strftime("%d/%m/%Y")

    for idx, raw in enumerate(rows, start=1):
        row = normalize_training_row(raw)
        curso = normalizar_curso_capacitacion_maestro(row.get("curso"))
        modalidad = normalizar_modalidad_capacitacion_maestro(row.get("modalidad"))
        fecha_actualizacion = format_date_label(row.get("fecha_actualizacion") or fecha_default) or fecha_default

        if not curso:
            errores.append({
                "fila": idx,
                "motivo": "curso_faltante",
                "nombre": row.get("nombre", ""),
                "correo": row.get("correo", ""),
            })
            continue

        if not curso_maestro_es_oficial(curso):
            pendientes.append({
                "id": row.get("id", ""),
                "nombre": row.get("nombre", ""),
                "correo": normalize_email(row.get("correo")),
                "carrera": row.get("carrera", "") or "No disponible",
                "division": row.get("division", "") or "No disponible",
                "curso": curso,
                "modalidad": modalidad,
                "fecha_actualizacion": fecha_actualizacion,
                "duracion": "",
                "minutos_num": "",
                "motivo": "curso_no_oficial",
                "archivo_origen": metadata.get("filename", ""),
                "hora_unio": "",
            })
            continue

        _, user, match_type = resolve_person(row, by_id, by_email, by_name)
        if not user:
            pendientes.append({
                "id": row.get("id", ""),
                "nombre": row.get("nombre", ""),
                "correo": normalize_email(row.get("correo")),
                "carrera": row.get("carrera", "") or "No disponible",
                "division": row.get("division", "") or "No disponible",
                "curso": curso,
                "modalidad": modalidad,
                "fecha_actualizacion": fecha_actualizacion,
                "duracion": "",
                "minutos_num": "",
                "motivo": "sin_coincidencia_base_maestros",
                "archivo_origen": metadata.get("filename", ""),
                "hora_unio": "",
            })
            continue

        validos.append({
            "id": user.get("id", "") or row.get("id", ""),
            "nombre": user.get("nombre", "") or row.get("nombre", ""),
            "correo": normalize_email(user.get("correo", "") or row.get("correo", "")),
            "carrera": user.get("carrera", "") or row.get("carrera", "") or "No disponible",
            "division": user.get("division", "") or row.get("division", "") or "No disponible",
            "curso": curso,
            "modalidad": modalidad,
            "fecha_actualizacion": fecha_actualizacion,
            "origen": metadata.get("origen") or CAPACITACIONES_API_ORIGEN,
            "observacion": f"Importado por API de capacitaciones ({match_type})",
        })

    return {
        "recibidos": len(rows),
        "validos": validos,
        "pendientes": pendientes,
        "errores": errores,
    }


def registrar_ingesta_capacitaciones_mysql(conexion, *, ingesta_key: str, metadata: dict[str, str], estado: str, detalle: str) -> None:
    from database_mysql import ejecutar

    ahora = mexico_now().strftime("%Y-%m-%d %H:%M:%S")
    ejecutar(
        conexion,
        """
        INSERT INTO ingestas (
            ingesta_key, tipo, mensaje_id, recurso_id, archivo, origen, asunto,
            fecha_reunion, fecha_descarga, estado, detalle, creado_en, actualizado_en
        ) VALUES (
            :ingesta_key, :tipo, :mensaje_id, :recurso_id, :archivo, :origen, :asunto,
            :fecha_reunion, :fecha_descarga, :estado, :detalle, :creado_en, :actualizado_en
        )
        ON DUPLICATE KEY UPDATE
            estado = VALUES(estado),
            detalle = VALUES(detalle),
            actualizado_en = VALUES(actualizado_en)
        """,
        {
            "ingesta_key": ingesta_key,
            "tipo": "maestros",
            "mensaje_id": metadata.get("ingesta_id", ""),
            "recurso_id": "api_capacitaciones",
            "archivo": metadata.get("filename", ""),
            "origen": metadata.get("origen") or CAPACITACIONES_API_ORIGEN,
            "asunto": metadata.get("asunto", ""),
            "fecha_reunion": "",
            "fecha_descarga": mexico_now_label(),
            "estado": estado,
            "detalle": detalle,
            "creado_en": ahora,
            "actualizado_en": ahora,
        },
    )


def importar_capacitaciones_maestros_api(metadata: dict[str, str], rows: list[dict[str, Any]], content: bytes) -> dict[str, Any]:
    if not database_url_configurada():
        raise RuntimeError("La API de capacitaciones requiere una base de datos configurada.")

    filename = clean(metadata.get("filename", "")) or "capacitaciones_maestros_en_linea.csv"
    if not filename.lower().endswith(".csv"):
        filename = f"{Path(filename).stem or 'capacitaciones_maestros_en_linea'}.csv"
    metadata["filename"] = secure_filename(filename) or "capacitaciones_maestros_en_linea.csv"
    metadata["origen"] = clean(metadata.get("origen")) or CAPACITACIONES_API_ORIGEN
    metadata["archivo_origen_db"] = f"{metadata['origen']}:{metadata['filename']}"

    content_hash = hashlib.sha256(content or json.dumps(rows, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    ingesta_key = f"api_capacitaciones:{metadata.get('ingesta_id') or content_hash}"

    preparados = preparar_registros_capacitaciones_maestros(rows, metadata)
    detalle = {
        "recibidos": preparados["recibidos"],
        "validos": len(preparados["validos"]),
        "pendientes": len(preparados["pendientes"]),
        "errores": len(preparados["errores"]),
    }

    from database_mysql import (
        crear_engine_mysql,
        ejecutar,
        inicializar_mysql,
        insertar_auxiliar_mysql,
        upsert_capacitacion_mysql,
    )

    engine = crear_engine_mysql()
    with engine.begin() as conexion:
        inicializar_mysql(conexion)

        ejecutar(
            conexion,
            "DELETE FROM pendientes_revision WHERE tipo = 'maestro' AND archivo_origen = :archivo",
            {"archivo": metadata["archivo_origen_db"]},
        )

        for fila in preparados["validos"]:
            upsert_capacitacion_mysql(
                conexion,
                tipo="maestro",
                id_externo=fila.get("id", ""),
                nombre=fila.get("nombre", ""),
                correo=fila.get("correo", ""),
                carrera=fila.get("carrera", ""),
                division=fila.get("division", ""),
                curso=fila.get("curso", ""),
                modalidad=fila.get("modalidad", "En línea"),
                fecha_actualizacion=fila.get("fecha_actualizacion", ""),
                fuente=metadata["origen"],
                archivo_origen=metadata["archivo_origen_db"],
            )

        for fila in preparados["pendientes"]:
            fila["archivo_origen"] = metadata["archivo_origen_db"]
            insertar_auxiliar_mysql(conexion, "pendientes_revision", tipo="maestro", fila=fila)

        estado = "procesado" if not preparados["errores"] else "procesado_con_observaciones"
        registrar_ingesta_capacitaciones_mysql(
            conexion,
            ingesta_key=ingesta_key,
            metadata=metadata,
            estado=estado,
            detalle=json.dumps(detalle, ensure_ascii=False),
        )

    set_report_update_timestamp("maestro", origen="api_capacitaciones_en_linea")
    try:
        cache = regenerate_report_cache_for_tipo("maestro")
    except Exception as exc:
        cache = {
            "cache_enabled": REPORT_CACHE_ENABLED,
            "error": f"No se pudo regenerar cache maestros: {exc}",
        }

    return {
        "ok": True,
        "tipo": "maestros",
        "origen": metadata["origen"],
        "filename": metadata["filename"],
        "ingesta_key": ingesta_key,
        "recibidos": preparados["recibidos"],
        "validos": len(preparados["validos"]),
        "pendientes": len(preparados["pendientes"]),
        "errores": preparados["errores"],
        "cache": cache,
    }



def read_direct_meet_upload_payload() -> tuple[dict[str, str], bytes]:
    metadata: dict[str, str] = {}
    content: bytes = b""

    if request.is_json:
        data = request.get_json(silent=True) or {}
        metadata = {
            "tipo": clean(data.get("tipo", "")),
            "subject": clean(data.get("subject", data.get("asunto", ""))),
            "filename": clean(data.get("filename", data.get("archivo", ""))),
            "fecha_reunion": clean(data.get("fecha_reunion", data.get("fecha", ""))),
            "curso": clean(data.get("curso", "")),
            "ingesta_id": clean(data.get("ingesta_id", data.get("message_id", data.get("mensaje_id", "")))),
        }

        csv_base64 = clean(data.get("csv_base64", ""))
        if csv_base64:
            padded = csv_base64 + "=" * (-len(csv_base64) % 4)
            content = base64.b64decode(padded.encode("utf-8"))
        else:
            csv_text = data.get("csv", data.get("csv_text", ""))
            content = str(csv_text or "").encode("utf-8-sig")

        return metadata, content

    metadata = {
        "tipo": clean(request.form.get("tipo", "")),
        "subject": clean(request.form.get("subject", request.form.get("asunto", ""))),
        "filename": clean(request.form.get("filename", request.form.get("archivo", ""))),
        "fecha_reunion": clean(request.form.get("fecha_reunion", request.form.get("fecha", ""))),
        "curso": clean(request.form.get("curso", "")),
        "ingesta_id": clean(request.form.get("ingesta_id", request.form.get("message_id", request.form.get("mensaje_id", "")))),
    }

    uploaded_file = request.files.get("archivo") or request.files.get("file") or request.files.get("csv")
    if uploaded_file and uploaded_file.filename:
        metadata["filename"] = metadata["filename"] or uploaded_file.filename
        content = uploaded_file.read()
    else:
        csv_base64 = clean(request.form.get("csv_base64", ""))
        if csv_base64:
            padded = csv_base64 + "=" * (-len(csv_base64) % 4)
            content = base64.b64decode(padded.encode("utf-8"))
        else:
            content = str(request.form.get("csv", request.form.get("csv_text", "")) or "").encode("utf-8-sig")

    return metadata, content


def save_direct_meet_csv(tipo: str, filename: str, content: bytes) -> Path:
    if not content:
        raise MeetAutomationError("No se recibió contenido CSV.")

    filename = filename or "asistencia_meet.csv"
    if not filename.lower().endswith(".csv"):
        filename = f"{Path(filename).stem or 'asistencia_meet'}.csv"

    target_dir = get_meet_target_dir(tipo)
    target_dir.mkdir(parents=True, exist_ok=True)
    destination = target_dir / safe_download_filename(f"api_{get_meet_target_prefix(tipo)}", filename)
    destination.write_bytes(content)
    return destination


def process_direct_meet_upload(metadata: dict[str, str], content: bytes) -> dict[str, Any]:
    subject = clean(metadata.get("subject", ""))
    tipo = normalize_meet_tipo(metadata.get("tipo", ""), subject)
    filename = clean(metadata.get("filename", "")) or "asistencia_meet.csv"
    fecha_reunion = clean(metadata.get("fecha_reunion", "")) or parse_meet_subject_date(subject)
    curso = clean(metadata.get("curso", "")) or ALUMNOS_CURSO_OFICIAL
    ingesta_id = clean(metadata.get("ingesta_id", ""))

    if ingesta_id:
        processed_key = (f"api:{ingesta_id}", "direct_csv")
        if processed_key in read_processed_meet_records():
            return {
                "ok": True,
                "duplicado": True,
                "tipo": tipo,
                "ingesta_id": ingesta_id,
                "mensaje": "Esta ingesta ya había sido procesada.",
            }

    saved_path = save_direct_meet_csv(tipo, filename, content)

    if tipo == "maestros":
        resultado = process_meet_maestros_csv_batch([(saved_path, fecha_reunion, subject or saved_path.name)])
    else:
        resultado = process_meet_csv_batch([(saved_path, fecha_reunion)], curso=curso)
        if MEET_API_MOVE_PROCESSED_FILES:
            move_files_to_processed_folder([saved_path])

    if ingesta_id:
        append_processed_meet_records([{
            "mensaje_id": f"api:{ingesta_id}",
            "recurso_id": "direct_csv",
            "archivo": saved_path.name,
            "origen": "api_directa",
            "asunto": subject,
            "fecha_reunion": fecha_reunion,
            "fecha_descarga": mexico_now_label(),
            "estado": "procesado",
            "tipo": tipo,
            "detalle": build_ingesta_detalle_json(tipo, resultado),
        }])

    try:
        resultado_bd = sincronizar_bd_meet_api_ligero(tipo, resultado=resultado)
        advertencia_bd = ""
    except Exception as exc:
        resultado_bd = {
            "ok": False,
            "error": f"La asistencia se procesó, pero no se pudo actualizar BD/cache: {exc}",
        }
        advertencia_bd = resultado_bd["error"]

    resultado_publico = {key: value for key, value in resultado.items() if not key.startswith("_")}

    response_payload = {
        "ok": True,
        "duplicado": False,
        "tipo": tipo,
        "archivo": saved_path.name,
        "fecha_reunion": fecha_reunion,
        "resultado": resultado_publico,
        "bd": resultado_bd,
    }
    if advertencia_bd:
        response_payload["advertencia"] = advertencia_bd

    return response_payload



def build_ingesta_detalle_json(tipo: str, resultado: dict[str, Any] | None = None, error: str = "") -> str:
    resultado = resultado or {}
    tipo_norm = clean(tipo).lower()

    if tipo_norm == "maestros":
        conteos = {
            "procesados": resultado.get("procesados_maestros", 0),
            "validos": resultado.get("validos_maestros", 0),
            "pendientes": resultado.get("pendientes_maestros", 0),
            "descartados": resultado.get("descartados_maestros", 0),
            "total_capacitaciones": resultado.get("total_capacitaciones_maestros", 0),
        }
    else:
        conteos = {
            "procesados": resultado.get("procesados", 0),
            "validos": resultado.get("validos", 0),
            "pendientes": resultado.get("pendientes", 0),
            "descartados": resultado.get("descartados", 0),
            "total_capacitaciones": resultado.get("total_capacitaciones", 0),
        }

    payload = {
        "conteos": conteos,
    }

    if error:
        payload["error"] = clean(error)

    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def parse_ingesta_detalle(detalle: Any) -> dict[str, Any]:
    texto = clean(detalle)
    if not texto:
        return {}

    try:
        parsed = json.loads(texto)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {"mensaje": texto}


def enrich_ingesta_row(row: dict[str, Any]) -> dict[str, Any]:
    item = {key: clean(value) for key, value in row.items()}
    detalle = parse_ingesta_detalle(item.get("detalle", ""))
    conteos = detalle.get("conteos", {}) if isinstance(detalle.get("conteos", {}), dict) else {}

    item["procesados"] = int(float(conteos.get("procesados") or 0))
    item["validos"] = int(float(conteos.get("validos") or 0))
    item["pendientes"] = int(float(conteos.get("pendientes") or 0))
    item["descartados"] = int(float(conteos.get("descartados") or 0))
    item["error"] = clean(detalle.get("error", ""))
    item["mensaje_detalle"] = clean(detalle.get("mensaje", ""))
    item["es_error"] = clean(item.get("estado", "")).lower().startswith("error") or bool(item["error"])
    item["fecha_orden"] = parse_datetime_flexible(
        item.get("fecha_descarga")
        or item.get("actualizado_en")
        or item.get("creado_en")
    ).isoformat()
    return item


def ordenar_ingestas_admin(rows: list[dict[str, Any]], limite: int) -> list[dict[str, Any]]:
    enriquecidas = [enrich_ingesta_row(row) for row in rows]

    # El panel admin está enfocado en el flujo principal actual:
    # Apps Script -> API directa -> Render/MySQL.
    # El historial viejo de adjuntos CSV se conserva en BD como respaldo,
    # pero no se muestra para no mezclarlo con las ingestas reales nuevas.
    solo_api_directa = [
        item for item in enriquecidas
        if norm(item.get("origen")) == "api_directa"
    ]

    def key(item: dict[str, Any]) -> datetime:
        return parse_datetime_flexible(
            item.get("fecha_descarga")
            or item.get("fecha_orden")
            or item.get("actualizado_en")
            or item.get("creado_en")
        )

    return sorted(solo_api_directa, key=key, reverse=True)[:limite]


def leer_ingestas_recientes_admin(limite: int = 12) -> list[dict[str, Any]]:
    limite_busqueda = max(limite * 5, 100)
    try:
        if database_url_configurada():
            from database_mysql import leer_ingestas_recientes_mysql

            rows = leer_ingestas_recientes_mysql(limite=limite_busqueda)
        else:
            from database import leer_ingestas_recientes

            rows = leer_ingestas_recientes(limite=limite_busqueda)

        return ordenar_ingestas_admin(rows, limite)
    except Exception as exc:
        print(f"AVISO: No se pudieron leer ingestas desde BD. Usando CSV. Detalle: {exc}", file=sys.stderr)

    if not ALUMNOS_MEET_PROCESADOS_PATH.exists():
        return []

    try:
        with ALUMNOS_MEET_PROCESADOS_PATH.open("r", encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))
    except Exception as exc:
        print(f"AVISO: No se pudo leer historial de ingestas CSV. Detalle: {exc}", file=sys.stderr)
        return []

    return ordenar_ingestas_admin(rows, limite)









def move_files_to_processed_folder(files: list[Path], folder_name: str = "procesados") -> list[Path]:
    moved: list[Path] = []

    for source_path in files:
        if not source_path.exists():
            continue

        target_dir = source_path.parent / folder_name
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / source_path.name

        if target_path.exists():
            stem = source_path.stem
            suffix = source_path.suffix
            counter = 2
            while target_path.exists():
                target_path = target_dir / f"{stem}_{counter}{suffix}"
                counter += 1

        source_path.replace(target_path)
        moved.append(target_path)

    return moved








def process_meet_csv_batch(
    source_files: list[tuple[Path, str]],
    curso: str,
) -> dict[str, Any]:
    users = read_users(ALUMNOS_USUARIOS_PATH)
    _, by_email, _ = build_user_indexes(users)

    existing_rows = read_capacitaciones(ALUMNOS_CAPACITACIONES_PATH)
    nuevos: list[dict[str, str]] = []
    pendientes: list[dict[str, Any]] = []
    descartados: list[dict[str, Any]] = []

    for source_path, fecha_actualizacion in source_files:
        fecha_default = format_date_label(fecha_actualizacion)

        with source_path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)

            for raw_row in reader:
                meet_row = normalize_meet_row(raw_row)
                nombre = clean(meet_row.get("nombre", "")).upper()
                correo = normalize_email(meet_row.get("correo", ""))
                duracion_texto = meet_row.get("duracion", "")
                minutos = parse_duration_minutes(duracion_texto)
                fecha = format_date_label(meet_row.get("fecha_actualizacion") or fecha_default)

                base_record = by_email.get(correo) if correo else None

                registro_base = {
                    "id": base_record.get("id", "") if base_record else "",
                    "nombre": base_record.get("nombre", "") if base_record else nombre,
                    "correo": base_record.get("correo", "") if base_record else correo,
                    "curso": curso,
                    "modalidad": "A distancia",
                    "fecha_actualizacion": fecha,
                    "duracion": duracion_texto,
                    "minutos_num": "" if minutos is None else round(minutos, 2),
                    "archivo_origen": source_path.name,
                    "hora_unio": clean(meet_row.get("hora_unio", "")),
                }

                if not correo:
                    pendientes.append({**registro_base, "motivo": "sin_correo"})
                    continue

                if not base_record:
                    pendientes.append({**registro_base, "motivo": "correo_no_en_base_alumnos"})
                    continue

                if minutos is None:
                    pendientes.append({**registro_base, "motivo": "duracion_no_valida"})
                    continue

                if minutos < ALUMNOS_MINUTOS_MINIMOS:
                    descartados.append({**registro_base, "motivo": f"menos_de_{ALUMNOS_MINUTOS_MINIMOS}_minutos"})
                    continue

                nuevos.append({
                    "id": base_record.get("id", ""),
                    "nombre": base_record.get("nombre", "") or nombre,
                    "correo": base_record.get("correo", "") or correo,
                    "curso": curso,
                    "modalidad": "A distancia",
                    "fecha_actualizacion": fecha,
                    "duracion": duracion_texto,
                    "minutos_num": "" if minutos is None else round(minutos, 2),
                    "archivo_origen": source_path.name,
                    "origen": "api_directa",
                })

    all_rows = deduplicate_training_rows(existing_rows + nuevos)

    write_csv(
        ALUMNOS_CAPACITACIONES_PATH,
        all_rows,
        ["id", "nombre", "correo", "curso", "modalidad", "fecha_actualizacion", "origen", "observacion"],
    )

    write_csv(
        ALUMNOS_PENDIENTES_PATH,
        pendientes,
        ["id", "nombre", "correo", "curso", "modalidad", "fecha_actualizacion", "duracion", "minutos_num", "motivo"],
    )

    write_csv(
        ALUMNOS_DESCARTADOS_PATH,
        descartados,
        ["id", "nombre", "correo", "curso", "modalidad", "fecha_actualizacion", "duracion", "minutos_num", "motivo"],
    )

    return {
        "procesados": len(nuevos) + len(pendientes) + len(descartados),
        "validos": len(nuevos),
        "pendientes": len(pendientes),
        "descartados": len(descartados),
        "total_capacitaciones": len(all_rows),
        "_validos_registros": nuevos,
        "_pendientes_registros": pendientes,
        "_descartados_registros": descartados,
        "_archivos_origen": [source_path.name for source_path, _ in source_files],
    }



def process_meet_maestros_csv_batch(
    source_files: list[tuple[Path, str, str]],
) -> dict[str, Any]:
    if not source_files:
        return {
            "procesados_maestros": 0,
            "validos_maestros": 0,
            "pendientes_maestros": 0,
            "descartados_maestros": 0,
            "total_capacitaciones_maestros": len(read_capacitaciones(CAPACITACIONES_PATH)),
        }

    users = read_users(USUARIOS_PATH)
    by_id, by_email, by_name = build_user_indexes(users)
    horarios = read_maestros_horarios()
    existing_rows = read_capacitaciones(CAPACITACIONES_PATH)

    nuevos: list[dict[str, str]] = []
    pendientes: list[dict[str, Any]] = []
    descartados: list[dict[str, Any]] = []
    processed_paths: list[Path] = []

    for source_path, fecha_reunion_label, subject in source_files:
        if not source_path.exists() or source_path.parent.name == "procesados":
            continue

        subject_for_date = subject or source_path.name
        fecha_reunion_dt = parse_meet_subject_datetime(subject_for_date)
        if not fecha_reunion_dt:
            fecha_reunion_dt = parse_date_value(fecha_reunion_label)

        fecha_default = format_date_label(fecha_reunion_dt.strftime("%d/%m/%Y") if fecha_reunion_dt else fecha_reunion_label)

        try:
            with source_path.open("r", encoding="utf-8-sig", newline="") as file:
                reader = csv.DictReader(file)
                for raw_row in reader:
                    meet_row = normalize_meet_row(raw_row)
                    nombre = clean(meet_row.get("nombre", "")).upper()
                    correo = normalize_email(meet_row.get("correo", ""))
                    duracion_texto = meet_row.get("duracion", "")
                    minutos = parse_duration_minutes(duracion_texto)
                    hora_unio = clean(meet_row.get("hora_unio", ""))
                    fecha = format_date_label(meet_row.get("fecha_actualizacion") or fecha_default)
                    horario = buscar_horario_maestro(horarios, fecha_reunion_dt, hora_unio)

                    base_record = by_email.get(correo) if correo else None
                    if not base_record and nombre:
                        base_record = by_name.get(norm(nombre))

                    registro_base = {
                        "id": base_record.get("id", "") if base_record else "",
                        "nombre": base_record.get("nombre", "") if base_record else nombre,
                        "correo": base_record.get("correo", "") if base_record else correo,
                        "carrera": base_record.get("carrera", "") if base_record else "No disponible",
                        "division": base_record.get("division", "") if base_record else "No disponible",
                        "curso": horario.get("curso", "") if horario else "",
                        "modalidad": horario.get("modalidad", "A distancia") if horario else "A distancia",
                        "fecha_actualizacion": horario.get("fecha_label", fecha) if horario else fecha,
                        "duracion": duracion_texto,
                        "minutos_num": "" if minutos is None else round(minutos, 2),
                        "archivo_origen": source_path.name,
                        "hora_unio": hora_unio,
                    }

                    if not correo:
                        pendientes.append({**registro_base, "motivo": "sin_correo"})
                        continue

                    if not base_record:
                        pendientes.append({**registro_base, "motivo": "correo_no_en_base_maestros"})
                        continue

                    if not horario:
                        pendientes.append({**registro_base, "motivo": "sin_horario_curso"})
                        continue

                    if minutos is None:
                        pendientes.append({**registro_base, "motivo": "duracion_no_valida"})
                        continue

                    if minutos < MAESTROS_MINUTOS_MINIMOS:
                        descartados.append({**registro_base, "motivo": f"menos_de_{MAESTROS_MINUTOS_MINIMOS}_minutos"})
                        continue

                    nuevos.append({
                        "id": base_record.get("id", ""),
                        "nombre": base_record.get("nombre", "") or nombre,
                        "correo": base_record.get("correo", "") or correo,
                        "carrera": base_record.get("carrera", "") or "No disponible",
                        "division": base_record.get("division", "") or "No disponible",
                        "curso": horario["curso"],
                        "modalidad": horario["modalidad"],
                        "fecha_actualizacion": horario.get("fecha_label", fecha),
                        "duracion": duracion_texto,
                        "minutos_num": "" if minutos is None else round(minutos, 2),
                        "archivo_origen": source_path.name,
                        "hora_unio": hora_unio,
                        "origen": "api_directa",
                    })
            processed_paths.append(source_path)
        except UnicodeDecodeError:
            pendientes.append({
                "id": "",
                "nombre": "",
                "correo": "",
                "carrera": "No disponible",
                "division": "No disponible",
                "curso": "",
                "modalidad": "A distancia",
                "fecha_actualizacion": fecha_default,
                "duracion": "",
                "minutos_num": "",
                "archivo_origen": source_path.name,
                "hora_unio": "",
                "motivo": "csv_no_utf8",
            })

    all_rows = deduplicate_training_rows(existing_rows + nuevos)

    write_csv(
        CAPACITACIONES_PATH,
        all_rows,
        ["id", "nombre", "correo", "carrera", "division", "curso", "modalidad", "fecha_actualizacion"],
    )

    maestro_aux_headers = [
        "id", "nombre", "correo", "carrera", "division", "curso", "modalidad",
        "fecha_actualizacion", "duracion", "minutos_num", "archivo_origen", "hora_unio", "motivo",
    ]

    write_csv(MAESTROS_PENDIENTES_MEET_PATH, pendientes, maestro_aux_headers)
    write_csv(MAESTROS_DESCARTADOS_MEET_PATH, descartados, maestro_aux_headers)

    if MEET_API_MOVE_PROCESSED_FILES and processed_paths:
        move_files_to_processed_folder(processed_paths)

    return {
        "procesados_maestros": len(nuevos) + len(pendientes) + len(descartados),
        "validos_maestros": len(nuevos),
        "pendientes_maestros": len(pendientes),
        "descartados_maestros": len(descartados),
        "total_capacitaciones_maestros": len(all_rows),
        "_validos_registros": nuevos,
        "_pendientes_registros": pendientes,
        "_descartados_registros": descartados,
        "_archivos_origen": [path.name for path in processed_paths],
    }

def process_meet_csv(
    source_path: Path,
    curso: str,
    fecha_actualizacion: str = "",
) -> dict[str, Any]:
    return process_meet_csv_batch(
        [(source_path, fecha_actualizacion)],
        curso=curso,
    )


def read_users(path: Path = USUARIOS_PATH) -> list[dict[str, str]]:
    if not path.exists():
        return []

    users: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for raw_row in reader:
            user = normalize_user_row(raw_row)
            if user["id"] or user["correo"] or user["nombre"]:
                users.append(user)
    return users


def read_capacitaciones(path: Path = CAPACITACIONES_PATH) -> list[dict[str, str]]:
    if not path.exists():
        return []

    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for raw_row in reader:
            row = normalize_training_row(raw_row)
            has_identifier = row["id"] or row["correo"] or row["nombre"]
            if has_identifier and row["curso"] and row["modalidad"]:
                rows.append(row)

    return sorted(rows, key=lambda item: parse_date(item["fecha_actualizacion"]), reverse=True)




def database_url_configurada() -> bool:
    return bool(os.getenv("DATABASE_URL", "").strip() or os.getenv("DB_HOST", "").strip())


def database_available_for_reports() -> bool:
    if not READ_REPORTS_FROM_DB:
        return False

    if database_url_configurada():
        return True

    try:
        from database import DATABASE_PATH
        return DATABASE_PATH.exists()
    except Exception:
        return False


def read_report_users(tipo: str = "maestro") -> list[dict[str, str]]:
    if database_available_for_reports():
        try:
            if database_url_configurada():
                from database_mysql import leer_usuarios_reporte_mysql

                users = leer_usuarios_reporte_mysql(tipo)
            else:
                from database import leer_usuarios_reporte

                users = leer_usuarios_reporte(tipo)

            if users:
                return users
        except Exception as exc:
            print(f"AVISO: No se pudieron leer usuarios desde BD. Usando CSV. Detalle: {exc}", file=sys.stderr)

    return read_users(ALUMNOS_USUARIOS_PATH if tipo == "alumno" else USUARIOS_PATH)


def read_report_capacitaciones(tipo: str = "maestro") -> list[dict[str, str]]:
    if database_available_for_reports():
        try:
            if database_url_configurada():
                from database_mysql import leer_capacitaciones_reporte_mysql

                rows = leer_capacitaciones_reporte_mysql(tipo)
            else:
                from database import leer_capacitaciones_reporte

                rows = leer_capacitaciones_reporte(tipo)

            if rows:
                return rows
        except Exception as exc:
            print(f"AVISO: No se pudieron leer capacitaciones desde BD. Usando CSV. Detalle: {exc}", file=sys.stderr)

    return read_capacitaciones(ALUMNOS_CAPACITACIONES_PATH if tipo == "alumno" else CAPACITACIONES_PATH)


def read_report_data(tipo: str = "maestro") -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    return read_report_capacitaciones(tipo), read_report_users(tipo)


def report_cache_path(tipo: str) -> Path:
    return ALUMNOS_REPORT_CACHE_PATH if tipo == "alumno" else MAESTROS_REPORT_CACHE_PATH


def read_report_cache(tipo: str) -> dict[str, Any] | None:
    if not REPORT_CACHE_ENABLED:
        return None

    path = report_cache_path(tipo)
    if not path.exists():
        return None

    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except Exception as exc:
        print(f"AVISO: No se pudo leer cache de reporte {tipo}. Detalle: {exc}", file=sys.stderr)
        return None

    if isinstance(payload, dict) and payload.get("reporte"):
        return payload["reporte"]

    if isinstance(payload, dict):
        return payload

    return None


def normalize_report_cache_tipo(tipo: str) -> str:
    texto = str(tipo or "").strip().lower()
    if texto in {"alumno", "alumnos"}:
        return "alumno"
    return "maestro"


def read_report_update_timestamps() -> dict[str, Any]:
    if not REPORT_UPDATE_TIMESTAMPS_PATH.exists():
        return {}

    try:
        with REPORT_UPDATE_TIMESTAMPS_PATH.open("r", encoding="utf-8") as file:
            payload = json.load(file)
            return payload if isinstance(payload, dict) else {}
    except Exception as exc:
        print(f"AVISO: No se pudo leer timestamps de reporte. Detalle: {exc}", file=sys.stderr)
        return {}


def write_report_update_timestamps(payload: dict[str, Any]) -> None:
    REPORT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = REPORT_UPDATE_TIMESTAMPS_PATH.with_suffix(".tmp")

    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, separators=(",", ":"))

    temp_path.replace(REPORT_UPDATE_TIMESTAMPS_PATH)


def set_report_update_timestamp(tipo: str, label: str | None = None, origen: str = "actualizacion_explicita") -> str:
    tipo_norm = normalize_report_cache_tipo(tipo)
    label = label or mexico_now_label()
    timestamps = read_report_update_timestamps()
    timestamps[tipo_norm] = {
        "label": label,
        "origen": clean(origen) or "actualizacion_explicita",
        "actualizado_en_iso": datetime.now(ZoneInfo("America/Mexico_City")).isoformat(timespec="seconds"),
    }
    write_report_update_timestamps(timestamps)
    return label


def get_report_update_timestamp_item(tipo: str) -> dict[str, Any]:
    timestamps = read_report_update_timestamps()
    item = timestamps.get(normalize_report_cache_tipo(tipo), {})
    if isinstance(item, str):
        return {"label": item, "origen": "actualizacion_explicita"}
    return item if isinstance(item, dict) else {}


def apply_report_update_timestamp(tipo: str, reporte: dict[str, Any]) -> dict[str, Any]:
    item = get_report_update_timestamp_item(tipo)
    label = clean(item.get("label", ""))
    if not label:
        return reporte

    stamped = dict(reporte)
    ultima_actualizacion_actual = clean(stamped.get("ultima_actualizacion", ""))

    if not clean(stamped.get("ultima_actualizacion_datos", "")) and ultima_actualizacion_actual != label:
        stamped["ultima_actualizacion_datos"] = ultima_actualizacion_actual

    stamped["ultima_actualizacion"] = label
    stamped["ultima_actualizacion_origen"] = clean(item.get("origen", "")) or "actualizacion_explicita"
    return stamped


def stamp_report_update_label(
    reporte: dict[str, Any],
    tipo: str | None = None,
    origen: str = "actualizacion_explicita",
) -> dict[str, Any]:
    """Marca el reporte con la hora real de una actualización explícita.

    Esta función solo debe usarse cuando sí ocurrió una acción real de
    actualización: sincronizar-bd, API directa de Meet o regeneración manual
    del cache desde admin. No debe ejecutarse por una visita normal al reporte,
    porque eso haría parecer que hubo datos nuevos solo por abrir la página o
    despertar Render.
    """
    label = mexico_now_label()
    if tipo:
        label = set_report_update_timestamp(tipo, label=label, origen=origen)

    stamped = dict(reporte)
    ultima_datos = stamped.get("ultima_actualizacion", "")
    if ultima_datos and ultima_datos != label:
        stamped["ultima_actualizacion_datos"] = ultima_datos
    stamped["ultima_actualizacion"] = label
    stamped["ultima_actualizacion_origen"] = clean(origen) or "actualizacion_explicita"
    return stamped


def write_report_cache(tipo: str, reporte: dict[str, Any]) -> None:
    if not REPORT_CACHE_ENABLED:
        return

    REPORT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = report_cache_path(tipo)
    temp_path = path.with_suffix(".tmp")
    payload = {
        "tipo": tipo,
        "generado_en": datetime.now(ZoneInfo("America/Mexico_City")).isoformat(timespec="seconds"),
        "backend": "mysql" if database_url_configurada() else "sqlite" if database_available_for_reports() else "csv",
        "reporte": reporte,
    }
    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, separators=(",", ":"))
    temp_path.replace(path)


def invalidate_report_cache(tipo: str | None = None) -> None:
    paths = [report_cache_path(tipo)] if tipo else [MAESTROS_REPORT_CACHE_PATH, ALUMNOS_REPORT_CACHE_PATH]
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except Exception as exc:
            print(f"AVISO: No se pudo eliminar cache {path}. Detalle: {exc}", file=sys.stderr)


def build_report_for_tipo(tipo: str) -> dict[str, Any]:
    rows, users = read_report_data(tipo)
    if tipo == "alumno":
        return build_report(
            rows,
            users,
            cursos_oficiales=ALUMNOS_CURSOS_OFICIALES,
            modalidades=ALUMNOS_MODALIDADES,
            cursos_requeridos=1,
            ultima_actualizacion_path=ALUMNOS_CAPACITACIONES_PATH,
            es_reporte_alumnos=True,
        )

    return build_report(
        rows,
        users,
        cursos_requeridos=6,
        cursos_para_completitud=CURSOS_OFICIALES[:6],
    )


def get_report_payload(
    tipo: str = "maestro",
    force_refresh: bool = False,
    mark_update: bool = False,
) -> dict[str, Any]:
    if REPORT_CACHE_ENABLED and not force_refresh:
        cached = read_report_cache(tipo)
        if cached:
            cached = apply_report_update_timestamp(tipo, cached)
            return cached

    reporte = build_report_for_tipo(tipo)
    if mark_update:
        reporte = stamp_report_update_label(reporte, tipo=tipo)
    else:
        reporte = apply_report_update_timestamp(tipo, reporte)
    write_report_cache(tipo, reporte)
    return reporte


def regenerate_report_cache() -> dict[str, Any]:
    invalidate_report_cache()
    maestros = get_report_payload("maestro", force_refresh=True, mark_update=True)
    alumnos = get_report_payload("alumno", force_refresh=True, mark_update=True)
    return {
        "cache_enabled": REPORT_CACHE_ENABLED,
        "maestros": {
            "total_personas": maestros.get("total_personas", 0),
            "total_registros": maestros.get("total_registros", 0),
            "cache": str(MAESTROS_REPORT_CACHE_PATH),
        },
        "alumnos": {
            "total_personas": alumnos.get("total_personas", 0),
            "total_registros": alumnos.get("total_registros", 0),
            "cache": str(ALUMNOS_REPORT_CACHE_PATH),
        },
    }


def regenerate_report_cache_for_tipo(tipo: str) -> dict[str, Any]:
    tipo = "alumno" if normalize_meet_tipo(tipo) == "alumnos" or clean(tipo).lower() == "alumno" else "maestro"
    invalidate_report_cache(tipo)
    reporte = get_report_payload(tipo, force_refresh=True, mark_update=True)
    return {
        "cache_enabled": REPORT_CACHE_ENABLED,
        "tipo": tipo,
        "total_personas": reporte.get("total_personas", 0),
        "total_registros": reporte.get("total_registros", 0),
        "cache": str(report_cache_path(tipo)),
    }



def regenerar_cache_remoto_si_configurado() -> dict[str, Any]:

    if not AUTO_REGENERAR_CACHE_REMOTO:
        return {"enabled": False, "ok": True, "mensaje": "AUTO_REGENERAR_CACHE_REMOTO deshabilitado."}

    if not PUBLIC_APP_URL:
        return {"enabled": True, "ok": False, "error": "Falta configurar PUBLIC_APP_URL."}

    if not REMOTE_CACHE_TOKEN:
        return {"enabled": True, "ok": False, "error": "Falta configurar REMOTE_CACHE_TOKEN o MEET_API_TOKEN."}

    url = f"{PUBLIC_APP_URL}/api/cache/regenerar"
    body = json.dumps({"origen": "sincronizar-bd"}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "Authorization": f"Bearer {REMOTE_CACHE_TOKEN}",
            "X-Meet-Api-Token": REMOTE_CACHE_TOKEN,
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=REMOTE_CACHE_TIMEOUT) as response:
            raw = response.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw)
            except Exception:
                payload = {"respuesta": raw}
            return {
                "enabled": True,
                "ok": 200 <= response.status < 300,
                "status": response.status,
                "url": url,
                "respuesta": payload,
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return {
            "enabled": True,
            "ok": False,
            "status": exc.code,
            "url": url,
            "error": raw,
        }
    except Exception as exc:
        return {
            "enabled": True,
            "ok": False,
            "url": url,
            "error": str(exc),
        }



def parse_float_safe(value: Any) -> float | None:
    texto = clean(value).replace(",", ".")
    if not texto:
        return None
    try:
        return float(texto)
    except ValueError:
        return None


def sincronizar_bd_meet_api_ligero(tipo: str, resultado: dict[str, Any] | None = None) -> dict[str, Any]:
    """Actualiza MySQL con solo la ingesta recién recibida por API.

    Antes esta función reimportaba el CSV completo de capacitaciones dentro de
    la llamada /api/meet/asistencia. En Render Free + Azure MySQL eso podía
    tardar demasiado y provocar WORKER TIMEOUT. Ahora usa los registros ya
    clasificados por process_meet_*_csv_batch y solamente hace UPSERT de la
    asistencia recibida.
    """
    tipo_normalizado = normalize_meet_tipo(tipo)
    tipo_db = "maestro" if tipo_normalizado == "maestros" else "alumno"
    cache_tipo = "maestro" if tipo_db == "maestro" else "alumno"
    resultado = resultado or {}

    if not database_url_configurada():
        resultado_sync = sincronizar_bd_desde_csv()
        resultado_sync["modo"] = "sincronizacion_completa_sqlite"
        return resultado_sync

    validos = list(resultado.get("_validos_registros") or [])
    pendientes = list(resultado.get("_pendientes_registros") or [])
    descartados = list(resultado.get("_descartados_registros") or [])
    archivos_origen = sorted({clean(nombre) for nombre in (resultado.get("_archivos_origen") or []) if clean(nombre)})

    # Si se llama sin registros clasificados, conservamos el comportamiento anterior
    # como respaldo para no romper flujos manuales.
    if not any([validos, pendientes, descartados]):
        from database_mysql import (
            crear_engine_mysql,
            ejecutar,
            importar_auxiliares_mysql,
            importar_capacitaciones_mysql,
            importar_ingestas_mysql,
            inicializar_mysql,
            resumen_mysql,
        )

        if tipo_db == "maestro":
            capacitaciones_path = CAPACITACIONES_PATH
            pendientes_path = MAESTROS_PENDIENTES_MEET_PATH
            descartados_path = MAESTROS_DESCARTADOS_MEET_PATH
        else:
            capacitaciones_path = ALUMNOS_CAPACITACIONES_PATH
            pendientes_path = ALUMNOS_PENDIENTES_PATH
            descartados_path = ALUMNOS_DESCARTADOS_PATH

        engine = crear_engine_mysql()
        with engine.begin() as conexion:
            inicializar_mysql(conexion)
            capacitaciones = importar_capacitaciones_mysql(conexion, capacitaciones_path, tipo_db)
            ejecutar(conexion, "DELETE FROM pendientes_revision WHERE tipo = :tipo", {"tipo": tipo_db})
            ejecutar(conexion, "DELETE FROM descartados WHERE tipo = :tipo", {"tipo": tipo_db})
            pendientes_total = importar_auxiliares_mysql(conexion, pendientes_path, tipo_db, "pendientes_revision")
            descartados_total = importar_auxiliares_mysql(conexion, descartados_path, tipo_db, "descartados")
            ingestas = importar_ingestas_mysql(conexion, ALUMNOS_MEET_PROCESADOS_PATH)
            resumen = resumen_mysql(conexion)

        set_report_update_timestamp(cache_tipo, origen="api_directa_meet")
        try:
            cache = regenerate_report_cache_for_tipo(cache_tipo)
        except Exception as exc:
            cache = {
                "cache_enabled": REPORT_CACHE_ENABLED,
                "error": f"No se pudo regenerar cache {cache_tipo}: {exc}",
            }

        return {
            "ok": True,
            "database_backend": "mysql",
            "modo": "respaldo_csv_completo",
            "tipo": tipo_db,
            "capacitaciones_importadas": capacitaciones,
            "pendientes_importados": pendientes_total,
            "descartados_importados": descartados_total,
            "ingestas_importadas": ingestas,
            "tablas": resumen,
            "cache": cache,
        }

    from database_mysql import (
        crear_engine_mysql,
        ejecutar,
        importar_ingestas_mysql,
        inicializar_mysql,
        insertar_auxiliar_mysql,
        resumen_mysql,
        upsert_capacitacion_mysql,
    )

    engine = crear_engine_mysql()
    with engine.begin() as conexion:
        inicializar_mysql(conexion)

        # Reemplazamos únicamente los pendientes/descartados de los archivos recibidos
        # en esta llamada. Así no borramos observaciones de otras sesiones.
        for archivo in archivos_origen:
            ejecutar(
                conexion,
                "DELETE FROM pendientes_revision WHERE tipo = :tipo AND archivo_origen = :archivo",
                {"tipo": tipo_db, "archivo": archivo},
            )
            ejecutar(
                conexion,
                "DELETE FROM descartados WHERE tipo = :tipo AND archivo_origen = :archivo",
                {"tipo": tipo_db, "archivo": archivo},
            )

        for fila in validos:
            upsert_capacitacion_mysql(
                conexion,
                tipo=tipo_db,
                id_externo=fila.get("id", ""),
                nombre=fila.get("nombre", ""),
                correo=fila.get("correo", ""),
                carrera=fila.get("carrera", "") or "No disponible",
                division=fila.get("division", "") or "No disponible",
                curso=fila.get("curso", ""),
                modalidad=fila.get("modalidad", ""),
                fecha_actualizacion=fila.get("fecha_actualizacion", ""),
                duracion_minutos=parse_float_safe(fila.get("minutos_num", "")),
                fuente="api_directa",
                archivo_origen=fila.get("archivo_origen", ""),
            )

        for fila in pendientes:
            insertar_auxiliar_mysql(conexion, "pendientes_revision", tipo=tipo_db, fila=fila)

        for fila in descartados:
            insertar_auxiliar_mysql(conexion, "descartados", tipo=tipo_db, fila=fila)

        # El historial es pequeño; importarlo completo conserva compatibilidad con el panel admin.
        ingestas = importar_ingestas_mysql(conexion, ALUMNOS_MEET_PROCESADOS_PATH)
        resumen = resumen_mysql(conexion)

    set_report_update_timestamp(cache_tipo, origen="api_directa_meet")
    try:
        cache = regenerate_report_cache_for_tipo(cache_tipo)
    except Exception as exc:
        cache = {
            "cache_enabled": REPORT_CACHE_ENABLED,
            "error": f"No se pudo regenerar cache {cache_tipo}: {exc}",
        }

    return {
        "ok": True,
        "database_backend": "mysql",
        "modo": "incremental_meet_api_ligero",
        "tipo": tipo_db,
        "capacitaciones_importadas": len(validos),
        "pendientes_importados": len(pendientes),
        "descartados_importados": len(descartados),
        "ingestas_importadas": ingestas,
        "archivos_origen": archivos_origen,
        "tablas": resumen,
        "cache": cache,
    }


def sync_bd_safe() -> dict[str, Any]:
    try:
        return sincronizar_bd_desde_csv()
    except Exception as exc:
        return {
            "ok": False,
            "error": f"No se pudo sincronizar la BD: {exc}",
        }

def build_user_indexes(users: list[dict[str, str]]) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    by_id: dict[str, dict[str, str]] = {}
    by_email: dict[str, dict[str, str]] = {}
    by_name: dict[str, dict[str, str]] = {}

    for user in users:
        if user["id"]:
            by_id[user["id"]] = user
        if user["correo"]:
            by_email[normalize_email(user["correo"])] = user
        if user["nombre"]:
            by_name[norm(user["nombre"])] = user

    return by_id, by_email, by_name


def resolve_person(row: dict[str, str], by_id: dict[str, dict[str, str]], by_email: dict[str, dict[str, str]], by_name: dict[str, dict[str, str]]) -> tuple[str, dict[str, str] | None, str]:
    if row["id"] and row["id"] in by_id:
        return row["id"], by_id[row["id"]], "id"

    email_key = normalize_email(row["correo"])
    if email_key and email_key in by_email:
        user = by_email[email_key]
        return user["id"] or email_key, user, "correo"

    name_key = norm(row["nombre"])
    if name_key and name_key in by_name:
        user = by_name[name_key]
        return user["id"] or user["correo"] or name_key, user, "nombre"

    fallback = row["id"] or email_key or name_key
    return fallback, None, "sin_coincidencia"


def es_revalidacion_alumno(row: dict[str, Any]) -> bool:
    modalidad = norm(str(row.get("modalidad", "")))
    origen = norm(str(row.get("origen", row.get("fuente", ""))))
    observacion = norm(str(row.get("observacion", "")))
    return "revalid" in modalidad or "revalid" in origen or "revalid" in observacion


def porcentaje_sobre_total(valor: int | float, total: int | float) -> float:
    total_num = float(total or 0)
    if total_num <= 0:
        return 0.0
    return round((float(valor or 0) / total_num) * 100, 1)


def build_report(
    rows: list[dict[str, str]],
    users: list[dict[str, str]],
    cursos_oficiales: list[str] | None = None,
    modalidades: list[str] | None = None,
    cursos_requeridos: int | None = None,
    ultima_actualizacion_path: Path = CAPACITACIONES_PATH,
    es_reporte_alumnos: bool = False,
    cursos_para_completitud: list[str] | None = None,
) -> dict[str, Any]:
    cursos_oficiales = cursos_oficiales or CURSOS_OFICIALES
    modalidades = modalidades or MODALIDADES
    cursos_requeridos = cursos_requeridos or len(cursos_oficiales)
    cursos_para_completitud = cursos_para_completitud or cursos_oficiales[:cursos_requeridos]
    cursos_completitud_norm = {norm(curso) for curso in cursos_para_completitud if norm(curso)}

    by_id, by_email, by_name = build_user_indexes(users)

    personas: dict[str, dict[str, Any]] = {}
    por_modalidad: dict[str, dict[str, list[dict[str, str]]]] = {
        modalidad: {curso: [] for curso in cursos_oficiales} for modalidad in modalidades
    }
    conteo_por_modalidad = {modalidad: 0 for modalidad in modalidades}
    conteo_por_curso_unico: dict[str, set[str]] = {curso: set() for curso in cursos_oficiales}
    registros_unicos_total: set[tuple[str, str]] = set()
    registros_sin_coincidencia: list[dict[str, str]] = []
    registros_detalle: list[dict[str, str]] = []

    for row in rows:
        persona_key, master_user, match_type = resolve_person(row, by_id, by_email, by_name)

        resolved = {
            "id": master_user["id"] if master_user and master_user["id"] else row["id"],
            "nombre": master_user["nombre"] if master_user and master_user["nombre"] else row["nombre"],
            "correo": master_user["correo"] if master_user and master_user["correo"] else row["correo"],
            "carrera": master_user.get("carrera", "") if master_user and master_user.get("carrera") else row.get("carrera", ""),
            "division": master_user.get("division", "") if master_user and master_user.get("division") else row.get("division", ""),
            "ml": "1" if user_has_materia_linea(master_user) else "0",
            "materia_linea": user_has_materia_linea(master_user),
            "curso": row["curso"],
            "modalidad": row["modalidad"],
            "fecha_actualizacion": row["fecha_actualizacion"],
            "origen": row.get("origen", row.get("fuente", "")),
            "observacion": row.get("observacion", ""),
            "coincidencia": match_type,
        }

        if match_type == "sin_coincidencia":
            registros_sin_coincidencia.append(resolved)

        registros_detalle.append({
            "id": resolved["id"],
            "nombre": resolved["nombre"] or "Sin nombre",
            "correo": resolved["correo"],
            "carrera": resolved.get("carrera", ""),
            "division": resolved.get("division", ""),
            "curso": resolved["curso"],
            "modalidad": resolved["modalidad"],
            "fecha_actualizacion": resolved["fecha_actualizacion"],
            "origen": resolved.get("origen", ""),
            "observacion": resolved.get("observacion", ""),
            "coincidencia": match_type,
            "ml": resolved.get("ml", "0"),
            "materia_linea": resolved.get("materia_linea", False),
        })

        # En alumnos, el reporte debe cruzarse contra la base activa.
        # Registros históricos de alumnos que ya no estén en la lista nueva
        # se conservan en BD/CSV, pero no cuentan en el total ni en el avance.
        if es_reporte_alumnos and users and not master_user:
            continue

        if persona_key not in personas:
            personas[persona_key] = {
                "id": resolved["id"],
                "nombre": resolved["nombre"] or "Sin nombre",
                "correo": resolved["correo"],
                "carrera": resolved.get("carrera", ""),
                "division": resolved.get("division", ""),
                "cursos": [],
                "total_cursos": 0,
                "completo": False,
                "ultima_actualizacion": resolved["fecha_actualizacion"],
                "origen": "base_maestra" if master_user else "capacitaciones",
                "en_base": bool(master_user),
                "tiene_revalidacion": False,
                "tiene_capacitacion_nueva": False,
                "tipo_cumplimiento": "pendiente",
                "ml": resolved.get("ml", "0"),
                "materia_linea": bool(resolved.get("materia_linea")),
            }

        es_revalidado = es_revalidacion_alumno(resolved) if es_reporte_alumnos else False

        personas[persona_key]["cursos"].append(
            {
                "curso": resolved["curso"],
                "modalidad": resolved["modalidad"],
                "fecha_actualizacion": resolved["fecha_actualizacion"],
                "carrera": resolved.get("carrera", ""),
                "division": resolved.get("division", ""),
                "origen": resolved.get("origen", ""),
                "observacion": resolved.get("observacion", ""),
                "es_revalidacion": es_revalidado,
            }
        )

        if es_reporte_alumnos:
            if es_revalidado:
                personas[persona_key]["tiene_revalidacion"] = True
            else:
                personas[persona_key]["tiene_capacitacion_nueva"] = True

        if not personas[persona_key].get("carrera") and resolved.get("carrera"):
            personas[persona_key]["carrera"] = resolved["carrera"]
        if not personas[persona_key].get("division") and resolved.get("division"):
            personas[persona_key]["division"] = resolved["division"]

        if parse_date(resolved["fecha_actualizacion"]) > parse_date(personas[persona_key]["ultima_actualizacion"]):
            personas[persona_key]["ultima_actualizacion"] = resolved["fecha_actualizacion"]

        modalidad = resolved["modalidad"]
        curso = resolved["curso"]

        if modalidad in por_modalidad:
            if curso not in por_modalidad[modalidad]:
                por_modalidad[modalidad][curso] = []
            por_modalidad[modalidad][curso].append(resolved)

        conteo_por_modalidad[modalidad] = conteo_por_modalidad.get(modalidad, 0) + 1

        curso_key = norm(curso)
        if curso_key:
            registros_unicos_total.add((persona_key, curso_key))
            if curso not in conteo_por_curso_unico:
                conteo_por_curso_unico[curso] = set()
            conteo_por_curso_unico[curso].add(persona_key)

    conteo_por_curso = {curso: len(personas_ids) for curso, personas_ids in conteo_por_curso_unico.items()}

    personas_lista = []
    for persona in personas.values():
        cursos_unicos = {curso["curso"] for curso in persona["cursos"]}
        cursos_unicos_norm = {norm(curso) for curso in cursos_unicos if norm(curso)}
        cursos_completitud_cubiertos = cursos_completitud_norm.intersection(cursos_unicos_norm)
        persona["total_cursos"] = len(cursos_completitud_cubiertos)
        persona["completo"] = bool(cursos_completitud_norm) and cursos_completitud_norm.issubset(cursos_unicos_norm)
        persona["pendientes"] = max(0, len(cursos_completitud_norm) - len(cursos_completitud_cubiertos))
        if es_reporte_alumnos:
            if persona["completo"] and persona.get("tiene_capacitacion_nueva"):
                persona["tipo_cumplimiento"] = "nuevo"
            elif persona["completo"] and persona.get("tiene_revalidacion"):
                persona["tipo_cumplimiento"] = "revalidado"
            else:
                persona["tipo_cumplimiento"] = "pendiente"
        persona["cursos"] = sorted(
            persona["cursos"],
            key=lambda item: parse_date(item["fecha_actualizacion"]),
            reverse=True,
        )
        personas_lista.append(persona)

    personas_lista.sort(key=lambda item: parse_date(item["ultima_actualizacion"]), reverse=True)

    ids_con_avance = {persona["id"] for persona in personas_lista if persona["id"]}
    correos_con_avance = {normalize_email(persona["correo"]) for persona in personas_lista if persona["correo"]}

    usuarios_sin_iniciar = []
    for user in users:
        user_id = user["id"]
        user_email = normalize_email(user["correo"])
        if (user_id and user_id in ids_con_avance) or (user_email and user_email in correos_con_avance):
            continue
        usuarios_sin_iniciar.append(user)

    total_usuarios_esperados = len(users)
    total_personas_reporte = total_usuarios_esperados if users else len(personas_lista)
    personas_con_avance = len(personas_lista)
    personas_completas = sum(1 for persona in personas_lista if persona["completo"])

    alumnos_revalidados = 0
    alumnos_nuevos_capacitados = 0
    alumnos_cumplidos_total = personas_completas
    alumnos_nuevos_esperados = 0
    alumnos_nuevos_pendientes = 0
    alumnos_porcentaje_revalidados = 0.0
    alumnos_porcentaje_nuevos = 0.0
    alumnos_porcentaje_cumplimiento = porcentaje_sobre_total(personas_completas, total_personas_reporte)

    if es_reporte_alumnos:
        alumnos_revalidados = sum(
            1
            for persona in personas_lista
            if persona["completo"] and persona.get("tipo_cumplimiento") == "revalidado"
        )
        alumnos_nuevos_capacitados = sum(
            1
            for persona in personas_lista
            if persona["completo"] and persona.get("tipo_cumplimiento") == "nuevo"
        )
        alumnos_cumplidos_total = alumnos_revalidados + alumnos_nuevos_capacitados
        personas_completas = alumnos_cumplidos_total
        alumnos_nuevos_esperados = max(0, total_personas_reporte - alumnos_revalidados)
        alumnos_nuevos_pendientes = max(0, alumnos_nuevos_esperados - alumnos_nuevos_capacitados)
        alumnos_porcentaje_revalidados = porcentaje_sobre_total(alumnos_revalidados, total_personas_reporte)
        alumnos_porcentaje_nuevos = porcentaje_sobre_total(alumnos_nuevos_capacitados, total_personas_reporte)
        alumnos_porcentaje_cumplimiento = porcentaje_sobre_total(alumnos_cumplidos_total, total_personas_reporte)

    cursos_1_y_2 = {norm(curso) for curso in cursos_oficiales[:2]}
    personas_con_cursos_1_y_2 = sum(
        1
        for persona in personas_lista
        if cursos_1_y_2.issubset({norm(curso["curso"]) for curso in persona["cursos"]})
    )

    curso_canvas7 = next(
        (curso for curso in cursos_oficiales if norm(curso).startswith("canvas 7") or "induccion para docentes" in norm(curso)),
        "",
    )
    curso_canvas7_norm = norm(curso_canvas7)
    usuarios_materia_linea = [user for user in users if user_has_materia_linea(user)]
    total_canvas7_materia_linea = len(usuarios_materia_linea)
    canvas7_completados_materia_linea = sum(
        1
        for persona in personas_lista
        if persona.get("materia_linea")
        and curso_canvas7_norm
        and any(norm(curso.get("curso")) == curso_canvas7_norm for curso in persona.get("cursos", []))
    )
    canvas7_porcentaje_materia_linea = porcentaje_sobre_total(
        canvas7_completados_materia_linea,
        total_canvas7_materia_linea,
    )

    personas_pendientes_con_avance = sum(1 for persona in personas_lista if not persona["completo"])

    if users:
        personas_pendientes = max(0, total_usuarios_esperados - personas_completas)
    else:
        personas_pendientes = personas_pendientes_con_avance

    if es_reporte_alumnos:
        personas_pendientes = max(0, total_personas_reporte - alumnos_cumplidos_total)

    return {
        "cursos_oficiales": cursos_oficiales,
        "modalidades": modalidades,
        "total_usuarios_esperados": total_usuarios_esperados,
        "total_personas": total_personas_reporte,
        "personas_con_avance": personas_con_avance,
        "usuarios_sin_iniciar": len(usuarios_sin_iniciar),
        "total_registros": len(registros_unicos_total),
        "total_registros_filas": len(rows),
        "personas_completas": personas_completas,
        "personas_con_cursos_1_y_2": personas_con_cursos_1_y_2,
        "curso_canvas7_materia_linea": curso_canvas7,
        "total_canvas7_materia_linea": total_canvas7_materia_linea,
        "canvas7_completados_materia_linea": canvas7_completados_materia_linea,
        "canvas7_porcentaje_materia_linea": canvas7_porcentaje_materia_linea,
        "personas_pendientes": personas_pendientes,
        "personas_pendientes_con_avance": personas_pendientes_con_avance,
        "alumnos_revalidados": alumnos_revalidados,
        "alumnos_nuevos_capacitados": alumnos_nuevos_capacitados,
        "alumnos_nuevos_esperados": alumnos_nuevos_esperados,
        "alumnos_nuevos_pendientes": alumnos_nuevos_pendientes,
        "alumnos_cumplidos_total": alumnos_cumplidos_total,
        "alumnos_porcentaje_revalidados": alumnos_porcentaje_revalidados,
        "alumnos_porcentaje_nuevos": alumnos_porcentaje_nuevos,
        "alumnos_porcentaje_cumplimiento": alumnos_porcentaje_cumplimiento,
        "conteo_por_modalidad": conteo_por_modalidad,
        "conteo_por_curso": conteo_por_curso,
        "por_modalidad": por_modalidad,
        "registros_detalle": sorted(registros_detalle, key=lambda item: parse_date(item["fecha_actualizacion"]), reverse=True),
        "personas": personas_lista,
        "usuarios_lista": sorted(users, key=lambda user: norm(user.get("nombre", ""))),
        "usuarios_sin_iniciar_lista": usuarios_sin_iniciar,
        "registros_sin_coincidencia": registros_sin_coincidencia,
        "total_registros_sin_coincidencia": len(registros_sin_coincidencia),
        "ultima_actualizacion": get_last_update_label(ultima_actualizacion_path),
        "usa_base_maestra": bool(users),
    }


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        password = request.form.get("password", "")
        if password == REPORT_PASSWORD:
            session["report_logged_in"] = True
            next_url = session.pop("next_url", url_for("index"))
            return redirect(next_url or url_for("index"))

        error = "Contraseña incorrecta."

    return render_template("login.html", error=error)


@app.route("/logout", methods=["GET", "POST"])
def logout_report():
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
@report_login_required
def index():
    return render_template("index.html", **template_context())


@app.get("/api/reporte")
@report_login_required
def api_reporte():
    return jsonify(get_report_payload("maestro"))


@app.get("/api/datos")
@report_login_required
def api_datos():
    rows, users = read_report_data("maestro")
    return jsonify({
        "capacitaciones": rows,
        "usuarios": users,
    })




@app.get("/alumnos")
@report_login_required
def alumnos():
    return render_template("alumnos.html", **template_context())


@app.get("/api/alumnos/reporte")
@report_login_required
def api_alumnos_reporte():
    return jsonify(get_report_payload("alumno"))


@app.get("/api/alumnos/datos")
@report_login_required
def api_alumnos_datos():
    rows, users = read_report_data("alumno")
    return jsonify({
        "capacitaciones": rows,
        "usuarios": users,
    })


@app.post("/api/meet/asistencia")
def api_meet_asistencia_directa():
    authorized, error = validate_meet_api_token()
    if not authorized:
        status_code = 503 if "Falta configurar" in error or "deshabilitada" in error else 401
        return jsonify({"ok": False, "error": error}), status_code

    try:
        metadata, content = read_direct_meet_upload_payload()
        resultado = process_direct_meet_upload(metadata, content)
    except MeetAutomationError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"No se pudo procesar la asistencia: {exc}"}), 500

    return jsonify(resultado)



@app.post("/api/maestros/capacitaciones/importar")
def api_maestros_capacitaciones_importar():
    authorized, error = validate_capacitaciones_api_token()
    if not authorized:
        status_code = 503 if "Falta configurar" in error or "deshabilitada" in error else 401
        return jsonify({"ok": False, "error": error}), status_code

    try:
        metadata, rows, content = read_capacitaciones_import_payload()
        if not rows:
            return jsonify({"ok": False, "error": "No se recibieron registros para importar."}), 400

        resultado = importar_capacitaciones_maestros_api(metadata, rows, content)
        return jsonify(resultado)
    except Exception as exc:
        return jsonify({"ok": False, "error": f"No se pudieron importar capacitaciones de maestros: {exc}"}), 500


@app.get("/api/maestros/capacitaciones/health")
def api_maestros_capacitaciones_health():
    return jsonify({
        "ok": True,
        "api_capacitaciones_habilitada": CAPACITACIONES_API_ENABLED,
        "token_configurado": bool(CAPACITACIONES_API_TOKEN),
        "backend": "mysql" if database_url_configurada() else "sqlite",
        "modalidad_default": CAPACITACIONES_API_MODALIDAD,
        "origen_default": CAPACITACIONES_API_ORIGEN,
    })



@app.get("/api/meet/health")
def api_meet_health():
    return jsonify({
        "ok": True,
        "api_directa_habilitada": MEET_API_DIRECT_ENABLED,
        "token_configurado": bool(MEET_API_TOKEN),
        "backend": "mysql" if database_url_configurada() else "sqlite",
    })


@app.route("/admin", methods=["GET", "POST"])
@report_login_required
def admin():
    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("admin_panel"))
        error = "Contraseña incorrecta."

    if session.get("admin_logged_in"):
        return redirect(url_for("admin_panel"))

    return render_template("admin.html", logged_in=False, error=error)


@app.get("/admin/panel")
@report_login_required
@login_required
def admin_panel():
    reporte = get_report_payload("maestro")
    ingestas = leer_ingestas_recientes_admin()
    return render_template("admin.html", logged_in=True, error=None, reporte=reporte, ingestas=ingestas)


@app.post("/admin/cache/regenerar")
@report_login_required
@login_required
def admin_regenerar_cache():
    try:
        cache = regenerate_report_cache()
        ok = True
        error = ""
    except Exception as exc:
        cache = {}
        ok = False
        error = f"No se pudo regenerar cache: {exc}"

    if wants_json_response():
        status = 200 if ok else 500
        return jsonify({"ok": ok, "cache": cache, "error": error}), status

    if not ok:
        reporte = get_report_payload("maestro")
        ingestas = leer_ingestas_recientes_admin()
        return render_template("admin.html", logged_in=True, error=error, reporte=reporte, ingestas=ingestas)

    return redirect(url_for("admin_panel", updated="cache"))



@app.post("/api/cache/regenerar")
def api_cache_regenerar():
    ok_token, token_error = validate_meet_api_token()
    if not ok_token:
        return jsonify({"ok": False, "error": token_error}), 401

    try:
        cache = regenerate_report_cache()
        return jsonify({"ok": True, "cache": cache})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"No se pudo regenerar cache: {exc}"}), 500


@app.get("/admin/api/ingestas")
@report_login_required
@login_required
def admin_api_ingestas():
    limite = request.args.get("limite", "12")
    try:
        limite_int = max(1, min(50, int(limite)))
    except ValueError:
        limite_int = 12
    return jsonify({"ok": True, "ingestas": leer_ingestas_recientes_admin(limite_int)})






def wants_json_response() -> bool:
    return request.headers.get("X-Requested-With") == "fetch" or "application/json" in request.headers.get("Accept", "")














def make_csv_response(filename: str, rows: list[dict[str, Any]], headers: list[str]) -> Response:
    output = []
    output.append(",".join(headers))
    for row in rows:
        values = []
        for header in headers:
            value = str(row.get(header, "") or "")
            value = value.replace('"', '""')
            values.append(f'"{value}"')
        output.append(",".join(values))

    csv_text = "\ufeff" + "\n".join(output)
    return Response(
        csv_text,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/admin/download/sin-coincidencia")
@report_login_required
@login_required
def download_sin_coincidencia():
    rows, users = read_report_data("maestro")
    reporte = build_report(rows, users)
    headers = ["id", "nombre", "correo", "curso", "modalidad", "fecha_actualizacion", "coincidencia"]
    return make_csv_response("registros_sin_coincidencia.csv", reporte["registros_sin_coincidencia"], headers)


@app.get("/admin/download/sin-iniciar")
@report_login_required
@login_required
def download_sin_iniciar():
    rows, users = read_report_data("maestro")
    reporte = build_report(rows, users)
    headers = ["id", "nombre", "correo"]
    return make_csv_response("usuarios_sin_iniciar.csv", reporte["usuarios_sin_iniciar_lista"], headers)


@app.get("/admin/download/completos")
@report_login_required
@login_required
def download_maestros_completos():
    rows, users = read_report_data("maestro")
    reporte = build_report(rows, users)
    maestros_completos = []

    for persona in reporte["personas"]:
        if not persona.get("completo"):
            continue

        maestros_completos.append({
            "id": persona.get("id", ""),
            "nombre": persona.get("nombre", ""),
            "correo": persona.get("correo", ""),
            "carrera": persona.get("carrera", ""),
            "division": persona.get("division", ""),
            "cursos_completados": persona.get("total_cursos", 0),
        })

    maestros_completos.sort(key=lambda item: norm(item.get("nombre", "")))

    headers = ["id", "nombre", "correo", "carrera", "division", "cursos_completados"]
    return make_csv_response("maestros_6_cursos_completos.csv", maestros_completos, headers)


@app.get("/admin/download/maestros/canvas7")
@report_login_required
@login_required
def download_maestros_canvas7():
    rows, users = read_report_data("maestro")
    reporte = build_report_for_tipo("maestro")

    curso_canvas7 = next(
        (curso for curso in reporte.get("cursos_oficiales", []) if clean(curso).startswith("CANVAS 7")),
        "CANVAS 7. INDUCCIÓN PARA DOCENTES (MATERIA EN LÍNEA).",
    )
    curso_canvas7_norm = norm(curso_canvas7)

    personas_por_id = {
        clean(persona.get("id")): persona
        for persona in reporte.get("personas", [])
        if clean(persona.get("id"))
    }
    personas_por_correo = {
        normalize_email(persona.get("correo")): persona
        for persona in reporte.get("personas", [])
        if normalize_email(persona.get("correo"))
    }

    salida = []
    usuarios_base = [
        usuario
        for usuario in (users or reporte.get("usuarios_lista", []))
        if user_has_materia_linea(usuario)
    ]

    for usuario in usuarios_base:
        usuario_id = clean(usuario.get("id"))
        usuario_correo = normalize_email(usuario.get("correo"))
        persona = personas_por_id.get(usuario_id) or personas_por_correo.get(usuario_correo)

        registro_canvas7 = None
        if persona:
            for curso in persona.get("cursos", []):
                if norm(curso.get("curso")) == curso_canvas7_norm:
                    if not registro_canvas7 or parse_date(curso.get("fecha_actualizacion", "")) > parse_date(registro_canvas7.get("fecha_actualizacion", "")):
                        registro_canvas7 = curso

        completado = bool(registro_canvas7)
        salida.append({
            "id": usuario_id,
            "nombre": clean(usuario.get("nombre")) or (clean(persona.get("nombre")) if persona else ""),
            "correo": usuario_correo or (normalize_email(persona.get("correo")) if persona else ""),
            "carrera": clean(usuario.get("carrera")) or (clean(persona.get("carrera")) if persona else ""),
            "division": clean(usuario.get("division")) or (clean(persona.get("division")) if persona else ""),
            "ml": "1",
            "curso": curso_canvas7,
            "estado": "Completo" if completado else "Pendiente",
            "fecha_actualizacion": registro_canvas7.get("fecha_actualizacion", "") if registro_canvas7 else "",
            "modalidad": registro_canvas7.get("modalidad", "") if registro_canvas7 else "",
            "origen": registro_canvas7.get("origen", "") if registro_canvas7 else "",
            "observacion": registro_canvas7.get("observacion", "") if registro_canvas7 else "",
        })

    salida.sort(key=lambda item: (item["estado"] != "Completo", norm(item.get("nombre", ""))))

    headers = [
        "id",
        "nombre",
        "correo",
        "carrera",
        "division",
        "ml",
        "curso",
        "estado",
        "fecha_actualizacion",
        "modalidad",
        "origen",
        "observacion",
    ]
    return make_csv_response("maestros_canvas7.csv", salida, headers)


AUXILIARES_DOWNLOAD_HEADERS = [
    "id",
    "nombre",
    "correo",
    "carrera",
    "division",
    "curso",
    "modalidad",
    "fecha_actualizacion",
    "duracion",
    "minutos_num",
    "archivo_origen",
    "hora_unio",
    "motivo",
]


def normalizar_tipo_auxiliar(tipo: str) -> tuple[str, str]:
    tipo_limpio = clean(tipo).lower()
    if tipo_limpio in {"maestros", "maestro"}:
        return "maestro", "maestros"
    if tipo_limpio in {"alumnos", "alumno"}:
        return "alumno", "alumnos"
    return tipo_limpio, tipo_limpio


def read_auxiliares_from_db(tabla: str, tipo: str) -> list[dict[str, Any]] | None:
    if tabla not in {"pendientes_revision", "descartados"}:
        return None

    if not database_available_for_reports() or not database_url_configurada():
        return None

    tipo_a, tipo_b = normalizar_tipo_auxiliar(tipo)

    try:
        from database_mysql import crear_engine_mysql, ejecutar, inicializar_mysql

        engine = crear_engine_mysql()
        with engine.connect() as conexion:
            inicializar_mysql(conexion)
            filas = ejecutar(
                conexion,
                f"""
                SELECT
                    id_externo, nombre, correo, carrera, division, curso, modalidad,
                    fecha_actualizacion, duracion, minutos_num, archivo_origen, hora_unio, motivo, creado_en
                FROM {tabla}
                WHERE tipo IN (:tipo_a, :tipo_b)
                ORDER BY creado_en DESC, archivo_origen DESC, nombre ASC
                """,
                {"tipo_a": tipo_a, "tipo_b": tipo_b},
            ).mappings().all()

        return [
            {
                "id": clean(fila.get("id_externo", "")),
                "nombre": clean(fila.get("nombre", "")),
                "correo": normalize_email(fila.get("correo", "")),
                "carrera": clean(fila.get("carrera", "")) or "No disponible",
                "division": clean(fila.get("division", "")) or "No disponible",
                "curso": clean(fila.get("curso", "")),
                "modalidad": clean(fila.get("modalidad", "")),
                "fecha_actualizacion": format_date_label(fila.get("fecha_actualizacion", "")) if clean(fila.get("fecha_actualizacion", "")) else "",
                "duracion": clean(fila.get("duracion", "")),
                "minutos_num": clean(fila.get("minutos_num", "")),
                "archivo_origen": clean(fila.get("archivo_origen", "")),
                "hora_unio": clean(fila.get("hora_unio", "")),
                "motivo": clean(fila.get("motivo", "")),
            }
            for fila in filas
        ]
    except Exception as exc:
        print(f"AVISO: No se pudieron leer auxiliares desde BD. Usando CSV. Detalle: {exc}", file=sys.stderr)
        return None


def read_auxiliares_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        return list(reader)


def download_auxiliares_csv_response(
    *,
    filename: str,
    tabla: str,
    tipo: str,
    fallback_path: Path,
    headers: list[str] | None = None,
) -> Response:
    headers = headers or AUXILIARES_DOWNLOAD_HEADERS
    rows = read_auxiliares_from_db(tabla, tipo)
    if rows is None:
        rows = read_auxiliares_csv(fallback_path)
    return make_csv_response(filename, rows, headers)


@app.get("/admin/download/alumnos/pendientes")
@report_login_required
@login_required
def download_alumnos_pendientes():
    return download_auxiliares_csv_response(
        filename="alumnos_pendientes_revision.csv",
        tabla="pendientes_revision",
        tipo="alumno",
        fallback_path=ALUMNOS_PENDIENTES_PATH,
    )


@app.get("/admin/download/alumnos/descartados")
@report_login_required
@login_required
def download_alumnos_descartados():
    return download_auxiliares_csv_response(
        filename="alumnos_descartados_menos_30_min.csv",
        tabla="descartados",
        tipo="alumno",
        fallback_path=ALUMNOS_DESCARTADOS_PATH,
    )


@app.get("/admin/download/alumnos/reporte")
@report_login_required
@login_required
def download_reporte_alumnos():
    rows, users = read_report_data("alumno")
    reporte = build_report(
        rows,
        users,
        cursos_oficiales=ALUMNOS_CURSOS_OFICIALES,
        modalidades=ALUMNOS_MODALIDADES,
        cursos_requeridos=len(ALUMNOS_CURSOS_OFICIALES),
        ultima_actualizacion_path=ALUMNOS_CAPACITACIONES_PATH,
        es_reporte_alumnos=True,
    )

    personas_por_id = {
        clean(persona.get("id")): persona
        for persona in reporte["personas"]
        if clean(persona.get("id"))
    }
    personas_por_correo = {
        normalize_email(persona.get("correo")): persona
        for persona in reporte["personas"]
        if normalize_email(persona.get("correo"))
    }

    salida = []
    for usuario in reporte["usuarios_lista"]:
        alumno_id = clean(usuario.get("id"))
        correo = normalize_email(usuario.get("correo"))
        persona = personas_por_id.get(alumno_id) or personas_por_correo.get(correo)

        if persona and persona.get("completo"):
            tipo_cumplimiento = persona.get("tipo_cumplimiento", "")
            if tipo_cumplimiento == "nuevo":
                estado = "Completo"
                categoria = "Capacitado nuevo"
            elif tipo_cumplimiento == "revalidado":
                estado = "Completo"
                categoria = "Revalidado"
            else:
                estado = "Completo"
                categoria = "Completo"
        else:
            tipo_cumplimiento = "pendiente"
            estado = "Sin completar"
            categoria = "Pendiente"

        cursos = persona.get("cursos", []) if persona else []
        curso_principal = cursos[0] if cursos else {}

        salida.append({
            "id": alumno_id,
            "nombre": clean(usuario.get("nombre")),
            "correo": correo,
            "estado": estado,
            "categoria": categoria,
            "tipo_cumplimiento": tipo_cumplimiento,
            "curso": curso_principal.get("curso", ALUMNOS_CURSO_OFICIAL if persona else ""),
            "modalidad": curso_principal.get("modalidad", ""),
            "fecha_actualizacion": persona.get("ultima_actualizacion", "") if persona else "",
            "origen": curso_principal.get("origen", ""),
            "observacion": curso_principal.get("observacion", ""),
            "total_cursos": persona.get("total_cursos", 0) if persona else 0,
            "pendientes": persona.get("pendientes", len(ALUMNOS_CURSOS_OFICIALES)) if persona else len(ALUMNOS_CURSOS_OFICIALES),
        })

    salida.sort(key=lambda item: (item["estado"] != "Sin completar", norm(item.get("nombre", ""))))

    headers = [
        "id",
        "nombre",
        "correo",
        "estado",
        "categoria",
        "tipo_cumplimiento",
        "curso",
        "modalidad",
        "fecha_actualizacion",
        "origen",
        "observacion",
        "total_cursos",
        "pendientes",
    ]
    return make_csv_response("reporte_alumnos_completo.csv", salida, headers)



@app.get("/admin/download/maestros/meet-pendientes")
@report_login_required
@login_required
def download_maestros_meet_pendientes():
    return download_auxiliares_csv_response(
        filename="maestros_meet_pendientes_revision.csv",
        tabla="pendientes_revision",
        tipo="maestro",
        fallback_path=MAESTROS_PENDIENTES_MEET_PATH,
    )


@app.get("/admin/download/maestros/meet-descartados")
@report_login_required
@login_required
def download_maestros_meet_descartados():
    return download_auxiliares_csv_response(
        filename="maestros_meet_descartados_menos_30_min.csv",
        tabla="descartados",
        tipo="maestro",
        fallback_path=MAESTROS_DESCARTADOS_MEET_PATH,
    )


@app.post("/admin/logout")
def logout():
    session.clear()
    return redirect(url_for("admin"))


def ensure_runtime_directories() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    ALUMNOS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    ALUMNOS_INSUMOS_DIR.mkdir(parents=True, exist_ok=True)
    MAESTROS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    MAESTROS_INSUMOS_MEET_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_CACHE_DIR.mkdir(parents=True, exist_ok=True)




def fecha_revalidacion_alumnos(value: str | None = None) -> str:
    if value:
        return format_date_label(value)
    return datetime.now(ZoneInfo("America/Mexico_City")).strftime("%d/%m/%Y")


def alumno_ya_tiene_curso(row: dict[str, str], curso: str) -> bool:
    return norm(row.get("curso")) == norm(curso)


def revalidar_alumnos_desde_base(fecha: str | None = None) -> dict[str, Any]:
    """Marca como revalidados a los alumnos activos actuales.

    La base activa sigue siendo data/alumnos/usuarios.csv. Este comando agrega
    registros a data/alumnos/capacitaciones.csv para quienes todavía no tienen
    el CURSO DE ALUMNOS registrado. No duplica alumnos que ya tengan el curso.
    """

    ensure_runtime_directories()

    usuarios = read_users(ALUMNOS_USUARIOS_PATH)
    capacitaciones_actuales = read_capacitaciones(ALUMNOS_CAPACITACIONES_PATH)

    existentes_por_id = {
        clean(row.get("id"))
        for row in capacitaciones_actuales
        if clean(row.get("id")) and alumno_ya_tiene_curso(row, ALUMNOS_CURSO_OFICIAL)
    }
    existentes_por_correo = {
        normalize_email(row.get("correo"))
        for row in capacitaciones_actuales
        if normalize_email(row.get("correo")) and alumno_ya_tiene_curso(row, ALUMNOS_CURSO_OFICIAL)
    }

    fecha_registro = fecha_revalidacion_alumnos(fecha)
    nuevos: list[dict[str, str]] = []
    omitidos = 0

    for usuario in usuarios:
        alumno_id = clean(usuario.get("id"))
        correo = normalize_email(usuario.get("correo"))

        if (alumno_id and alumno_id in existentes_por_id) or (correo and correo in existentes_por_correo):
            omitidos += 1
            continue

        nuevos.append({
            "id": alumno_id,
            "nombre": clean(usuario.get("nombre")),
            "correo": correo,
            "curso": ALUMNOS_CURSO_OFICIAL,
            "modalidad": ALUMNOS_MODALIDAD_REVALIDACION,
            "fecha_actualizacion": fecha_registro,
            "origen": ALUMNOS_REVALIDACION_ORIGEN,
            "observacion": ALUMNOS_REVALIDACION_OBSERVACION,
        })

    todas = deduplicate_training_rows(capacitaciones_actuales + nuevos)
    write_csv(
        ALUMNOS_CAPACITACIONES_PATH,
        todas,
        ["id", "nombre", "correo", "curso", "modalidad", "fecha_actualizacion", "origen", "observacion"],
    )

    return {
        "ok": True,
        "usuarios_activos": len(usuarios),
        "revalidaciones_agregadas": len(nuevos),
        "omitidos_por_ya_tener_curso": omitidos,
        "total_capacitaciones_alumnos": len(todas),
        "fecha_revalidacion": fecha_registro,
        "archivo": str(ALUMNOS_CAPACITACIONES_PATH),
    }


def run_revalidar_alumnos_cli() -> int:
    fecha = sys.argv[2].strip() if len(sys.argv) > 2 else None

    try:
        resultado = revalidar_alumnos_desde_base(fecha)
        resultado_bd = sincronizar_bd_desde_csv()
    except Exception as exc:
        print(f"ERROR: No se pudo revalidar alumnos: {exc}", file=sys.stderr)
        return 1

    salida = {
        "revalidacion": resultado,
        "bd": resultado_bd.get("resultado", {}),
        "cache_remoto": resultado_bd.get("cache_remoto", {}),
    }
    print(json.dumps(salida, ensure_ascii=False, indent=2))
    return 0


def sincronizar_bd_desde_csv() -> dict[str, Any]:
    from migrar_csv_a_bd import migrar_csv_a_bd

    resultado = migrar_csv_a_bd(reiniciar=True)
    backend = resultado.get("backend", "mysql" if database_url_configurada() else "sqlite")

    if backend == "mysql":
        destino = "MySQL/Azure"
    else:
        from database import DATABASE_PATH

        destino = str(DATABASE_PATH)

    try:
        cache = regenerate_report_cache()
    except Exception as exc:
        cache = {
            "cache_enabled": REPORT_CACHE_ENABLED,
            "error": f"No se pudo regenerar cache: {exc}",
        }

    cache_remoto = regenerar_cache_remoto_si_configurado()

    return {
        "ok": True,
        "database_backend": backend,
        "database_path": destino,
        "resultado": resultado,
        "cache": cache,
        "cache_remoto": cache_remoto,
    }




def run_migrar_bd_cli() -> int:
    ensure_runtime_directories()

    try:
        resultado_bd = sincronizar_bd_desde_csv()
    except Exception as exc:
        print(f"ERROR: No se pudo migrar a BD: {exc}", file=sys.stderr)
        return 1

    print(f"Base de datos generada/actualizada: {resultado_bd['database_path']}")
    print(json.dumps(resultado_bd["resultado"], ensure_ascii=False, indent=2))

    cache_remoto = resultado_bd.get("cache_remoto", {})
    if cache_remoto.get("enabled"):
        if cache_remoto.get("ok"):
            print("Cache remoto regenerado correctamente.")
        else:
            print(f"AVISO: No se pudo regenerar cache remoto: {cache_remoto.get('error')}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    comando = sys.argv[1].strip().lower() if len(sys.argv) > 1 else ""


    if comando in {"revalidar-alumnos", "revalidar-alumno", "revalidar", "alumnos-revalidar"}:
        raise SystemExit(run_revalidar_alumnos_cli())

    if comando in {"migrar-bd", "migrar-db", "bd", "db", "sincronizar-bd", "sync-bd", "sync-db"}:
        raise SystemExit(run_migrar_bd_cli())

    if comando in {"regenerar-cache", "cache", "reporte-cache"}:
        ensure_runtime_directories()
        print(json.dumps(regenerate_report_cache(), ensure_ascii=False, indent=2))
        raise SystemExit(0)

    ensure_runtime_directories()
    app.run(debug=True)
