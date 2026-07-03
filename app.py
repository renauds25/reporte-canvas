from __future__ import annotations

import base64
import csv
import html
import json
import io
import re
import os
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
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

GOOGLE_CREDENTIALS_PATH = BASE_DIR / os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
GOOGLE_TOKEN_PATH = BASE_DIR / os.getenv("GOOGLE_TOKEN_FILE", "token_gmail.json")
GMAIL_MEET_QUERY = os.getenv(
    "GMAIL_MEET_QUERY",
    'subject:"Asistencia procesada" has:attachment newer_than:60d',
)
GMAIL_MEET_MAX_RESULTS = int(os.getenv("GMAIL_MEET_MAX_RESULTS", "25"))
GMAIL_MEET_DRIVE_FALLBACK = os.getenv("GMAIL_MEET_DRIVE_FALLBACK", "0").strip().lower() in {"1", "true", "yes", "si", "sí"}
GMAIL_MEET_PROCESSED_LABEL = os.getenv("GMAIL_MEET_PROCESSED_LABEL", "meet_python_descargado")
GMAIL_MEET_ERROR_LABEL = os.getenv("GMAIL_MEET_ERROR_LABEL", "meet_python_error")
GMAIL_MEET_MOVE_PROCESSED_FILES = os.getenv("GMAIL_MEET_MOVE_PROCESSED_FILES", "1").strip().lower() in {"1", "true", "yes", "si", "sí"}
READ_REPORTS_FROM_DB = os.getenv("READ_REPORTS_FROM_DB", "1").strip().lower() in {"1", "true", "yes", "si", "sí"}

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
]

MODALIDADES_OFICIALES = [
    "Presencial",
    "En línea",
    "A distancia",
]

MODALIDADES = MODALIDADES_OFICIALES

ALUMNOS_CURSO_OFICIAL = os.getenv("ALUMNOS_CURSO_OFICIAL", "CURSO DE ALUMNOS")
ALUMNOS_CURSOS_OFICIALES = [ALUMNOS_CURSO_OFICIAL]
ALUMNOS_MODALIDADES = ["A distancia"]
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


def parse_date(value: str) -> datetime:
    value = clean(value)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
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


def normalize_user_row(row: dict[str, str]) -> dict[str, str]:
    return {
        "id": get_value(row, "id", "ID", "matricula", "matrícula", "numero", "número"),
        "nombre": get_value(row, "nombre", "Nombre", "name", "participante"),
        "correo": get_value(row, "correo", "Correo", "correo electronico", "correo electrónico", "Correo electrónico", "email", "mail", "e-mail"),
        "carrera": get_value(row, "carrera", "Carrera", "licenciatura", "Licenciatura", "programa", "Programa"),
        "division": get_value(row, "division", "División", "Division", "dirección", "Direccion", "area", "Área"),
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
        return datetime.now().strftime("%d/%m/%Y")

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue

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


def extract_message_header(message: dict[str, Any], header_name: str) -> str:
    headers = message.get("payload", {}).get("headers", [])
    for header in headers:
        if clean(header.get("name", "")).lower() == header_name.lower():
            return clean(header.get("value", ""))
    return ""


def decode_gmail_body(data: str) -> str:
    if not data:
        return ""
    padded = data + "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8", errors="replace")
    except Exception:
        return ""


def iter_gmail_parts(payload: dict[str, Any]):
    yield payload
    for part in payload.get("parts", []) or []:
        yield from iter_gmail_parts(part)


def extract_spreadsheet_ids_from_message(message: dict[str, Any]) -> list[str]:
    combined_text = []
    for part in iter_gmail_parts(message.get("payload", {})):
        mime_type = part.get("mimeType", "")
        body_data = part.get("body", {}).get("data", "")
        if body_data and mime_type in {"text/html", "text/plain"}:
            combined_text.append(decode_gmail_body(body_data))

    text = html.unescape("\n".join(combined_text))
    ids = re.findall(r"https://docs\.google\.com/spreadsheets/d/([A-Za-z0-9_-]+)", text)

    unique_ids = []
    seen = set()
    for spreadsheet_id in ids:
        if spreadsheet_id not in seen:
            seen.add(spreadsheet_id)
            unique_ids.append(spreadsheet_id)
    return unique_ids


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
    value = clean(value)

    if not value:
        return None

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue

    return None


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



def normalize_gmail_label_name(label_name: str) -> str:
    return clean(label_name) or "meet_python_descargado"


def ensure_gmail_query_excludes_labels(query: str, label_names: list[str]) -> str:
    query = clean(query)
    query_norm = norm(query)

    for label_name in label_names:
        label_name = normalize_gmail_label_name(label_name)
        label_token = f"label:{label_name}"
        negative_label_token = f"-label:{label_name}"

        if norm(label_token) in query_norm or norm(negative_label_token) in query_norm:
            continue

        query = f"{query} -label:{label_name}".strip()

    return query


def get_or_create_gmail_label(gmail_service, label_name: str) -> str:
    label_name = normalize_gmail_label_name(label_name)

    labels_response = gmail_service.users().labels().list(userId="me").execute()
    for label in labels_response.get("labels", []):
        if clean(label.get("name", "")).lower() == label_name.lower():
            return label.get("id", "")

    created = gmail_service.users().labels().create(
        userId="me",
        body={
            "name": label_name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        },
    ).execute()

    return created.get("id", "")


def add_gmail_label_to_message(gmail_service, message_id: str, label_id: str) -> None:
    if not message_id or not label_id:
        return

    gmail_service.users().messages().modify(
        userId="me",
        id=message_id,
        body={"addLabelIds": [label_id]},
    ).execute()


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


def get_google_services():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise MeetAutomationError(
            "Faltan dependencias de Google. Instala con: python -m pip install -r requirements.txt"
        ) from exc

    scopes = [
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/drive.readonly",
    ]

    if not GOOGLE_CREDENTIALS_PATH.exists():
        raise MeetAutomationError(
            f"No encontré {GOOGLE_CREDENTIALS_PATH.name}. Descarga el OAuth Client de Google Cloud "
            "y guárdalo en la raíz del proyecto."
        )

    creds = None
    if GOOGLE_TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(GOOGLE_TOKEN_PATH), scopes)
        if hasattr(creds, "has_scopes") and not creds.has_scopes(scopes):
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(GOOGLE_CREDENTIALS_PATH), scopes)
            creds = flow.run_local_server(port=0)

        GOOGLE_TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

    gmail_service = build("gmail", "v1", credentials=creds)
    drive_service = build("drive", "v3", credentials=creds)
    return gmail_service, drive_service


def download_google_sheet_as_csv(drive_service, spreadsheet_id: str, destination: Path) -> None:
    try:
        from googleapiclient.http import MediaIoBaseDownload
    except ImportError as exc:
        raise MeetAutomationError(
            "Faltan dependencias de Google. Instala con: python -m pip install -r requirements.txt"
        ) from exc

    request_media = drive_service.files().export_media(
        fileId=spreadsheet_id,
        mimeType="text/csv",
    )
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request_media)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    destination.write_bytes(buffer.getvalue())


def download_meet_reports_from_gmail(
    curso: str | None = None,
    query: str | None = None,
    max_results: int | None = None,
) -> dict[str, Any]:
    gmail_service, drive_service = get_google_services()
    curso = clean(curso) or ALUMNOS_CURSO_OFICIAL
    query = ensure_gmail_query_excludes_labels(
        query or GMAIL_MEET_QUERY,
        [GMAIL_MEET_PROCESSED_LABEL, GMAIL_MEET_ERROR_LABEL],
    )
    max_results = max_results or GMAIL_MEET_MAX_RESULTS

    processed_label_id = get_or_create_gmail_label(gmail_service, GMAIL_MEET_PROCESSED_LABEL)
    error_label_id = get_or_create_gmail_label(gmail_service, GMAIL_MEET_ERROR_LABEL)

    processed = read_processed_meet_records()
    downloaded_alumnos_files: list[tuple[Path, str]] = []
    downloaded_maestros_files: list[tuple[Path, str, str]] = []
    processed_rows: list[dict[str, Any]] = []
    skipped = 0
    sin_csv = 0
    errores_drive = 0
    correos_etiquetados = 0
    correos_error = 0
    archivos_movidos = 0

    response = gmail_service.users().messages().list(
        userId="me",
        q=query,
        maxResults=max_results,
    ).execute()

    messages = response.get("messages", [])
    ALUMNOS_INSUMOS_DIR.mkdir(parents=True, exist_ok=True)
    MAESTROS_INSUMOS_MEET_DIR.mkdir(parents=True, exist_ok=True)

    for message_summary in messages:
        message_id = message_summary.get("id", "")
        if not message_id:
            continue

        message = gmail_service.users().messages().get(
            userId="me",
            id=message_id,
            format="full",
        ).execute()

        subject = extract_message_header(message, "Subject")
        fecha_reunion = parse_meet_subject_date(subject, message.get("internalDate"))
        tipo = clasificar_meet_por_asunto(subject)
        target_dir = get_meet_target_dir(tipo)
        target_prefix = get_meet_target_prefix(tipo)
        csv_downloaded_for_message = 0
        message_has_error = False

        for part in iter_gmail_parts(message.get("payload", {})):
            filename = clean(part.get("filename"))
            attachment_id = part.get("body", {}).get("attachmentId")

            if not filename or not attachment_id or not filename.lower().endswith(".csv"):
                continue

            resource_id = f"attachment:{attachment_id}"
            if (message_id, resource_id) in processed:
                skipped += 1
                continue

            try:
                attachment = gmail_service.users().messages().attachments().get(
                    userId="me",
                    messageId=message_id,
                    id=attachment_id,
                ).execute()

                data = attachment.get("data", "")
                padded = data + "=" * (-len(data) % 4)
                content = base64.urlsafe_b64decode(padded.encode("utf-8"))

                destination = target_dir / safe_download_filename(target_prefix, filename)
                destination.write_bytes(content)
                csv_downloaded_for_message += 1

                if tipo == "alumnos":
                    downloaded_alumnos_files.append((destination, fecha_reunion))
                else:
                    downloaded_maestros_files.append((destination, fecha_reunion, subject))

                processed_rows.append({
                    "mensaje_id": message_id,
                    "recurso_id": resource_id,
                    "archivo": destination.name,
                    "origen": "adjunto_csv",
                    "asunto": subject,
                    "fecha_reunion": fecha_reunion,
                    "fecha_descarga": datetime.now().strftime("%d/%m/%Y %H:%M"),
                    "estado": "descargado",
                    "tipo": tipo,
                    "detalle": "CSV adjunto descargado",
                })
            except Exception as exc:
                message_has_error = True
                processed_rows.append({
                    "mensaje_id": message_id,
                    "recurso_id": resource_id,
                    "archivo": "",
                    "origen": "adjunto_csv",
                    "asunto": subject,
                    "fecha_reunion": fecha_reunion,
                    "fecha_descarga": datetime.now().strftime("%d/%m/%Y %H:%M"),
                    "estado": "error_adjunto",
                    "tipo": tipo,
                    "detalle": str(exc),
                })

        if csv_downloaded_for_message > 0 and not message_has_error:
            add_gmail_label_to_message(gmail_service, message_id, processed_label_id)
            correos_etiquetados += 1
            continue

        if csv_downloaded_for_message > 0 and message_has_error:
            add_gmail_label_to_message(gmail_service, message_id, error_label_id)
            correos_error += 1
            continue

        if not GMAIL_MEET_DRIVE_FALLBACK:
            sin_csv += 1
            processed_rows.append({
                "mensaje_id": message_id,
                "recurso_id": "sin_csv_adjunto",
                "archivo": "",
                "origen": "correo",
                "asunto": subject,
                "fecha_reunion": fecha_reunion,
                "fecha_descarga": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "estado": "omitido",
                "tipo": tipo,
                "detalle": "El correo no tenía CSV adjunto. Se omitió Drive para evitar errores de permisos.",
            })
            add_gmail_label_to_message(gmail_service, message_id, error_label_id)
            correos_error += 1
            continue

        sheets_downloaded_for_message = 0
        for spreadsheet_id in extract_spreadsheet_ids_from_message(message):
            resource_id = f"sheet:{spreadsheet_id}"
            if (message_id, resource_id) in processed:
                skipped += 1
                continue

            destination = target_dir / safe_download_filename(target_prefix, f"meet_{spreadsheet_id}.csv")
            try:
                download_google_sheet_as_csv(drive_service, spreadsheet_id, destination)
            except Exception as exc:
                errores_drive += 1
                message_has_error = True
                processed_rows.append({
                    "mensaje_id": message_id,
                    "recurso_id": resource_id,
                    "archivo": "",
                    "origen": "google_sheet",
                    "asunto": subject,
                    "fecha_reunion": fecha_reunion,
                    "fecha_descarga": datetime.now().strftime("%d/%m/%Y %H:%M"),
                    "estado": "error_drive",
                    "tipo": tipo,
                    "detalle": str(exc),
                })
                continue

            sheets_downloaded_for_message += 1
            if tipo == "alumnos":
                downloaded_alumnos_files.append((destination, fecha_reunion))
            else:
                downloaded_maestros_files.append((destination, fecha_reunion, subject))

            processed_rows.append({
                "mensaje_id": message_id,
                "recurso_id": resource_id,
                "archivo": destination.name,
                "origen": "google_sheet",
                "asunto": subject,
                "fecha_reunion": fecha_reunion,
                "fecha_descarga": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "estado": "descargado",
                "tipo": tipo,
                "detalle": "Google Sheet exportado a CSV",
            })

        if sheets_downloaded_for_message > 0 and not message_has_error:
            add_gmail_label_to_message(gmail_service, message_id, processed_label_id)
            correos_etiquetados += 1
        elif message_has_error:
            add_gmail_label_to_message(gmail_service, message_id, error_label_id)
            correos_error += 1

    append_processed_meet_records(processed_rows)

    resultado_proceso = process_meet_csv_batch(
        downloaded_alumnos_files,
        curso=curso,
    ) if downloaded_alumnos_files else {
        "procesados": 0,
        "validos": 0,
        "pendientes": 0,
        "descartados": 0,
        "total_capacitaciones": len(read_capacitaciones(ALUMNOS_CAPACITACIONES_PATH)),
    }

    archivos_maestros_pendientes = [
        (path, parse_meet_subject_date(path.name), path.name)
        for path in MAESTROS_INSUMOS_MEET_DIR.glob("*.csv")
        if path.is_file() and path.parent.name != "procesados"
    ]
    maestros_source_files = downloaded_maestros_files + [
        item for item in archivos_maestros_pendientes if item[0] not in {downloaded[0] for downloaded in downloaded_maestros_files}
    ]

    resultado_maestros = process_meet_maestros_csv_batch(maestros_source_files) if maestros_source_files else {
        "procesados_maestros": 0,
        "validos_maestros": 0,
        "pendientes_maestros": 0,
        "descartados_maestros": 0,
        "total_capacitaciones_maestros": len(read_capacitaciones(CAPACITACIONES_PATH)),
    }

    if GMAIL_MEET_MOVE_PROCESSED_FILES and downloaded_alumnos_files:
        moved_files = move_files_to_processed_folder([path for path, _ in downloaded_alumnos_files])
        archivos_movidos = len(moved_files)

    return {
        "correos_encontrados": len(messages),
        "archivos_descargados": len(downloaded_alumnos_files) + len(downloaded_maestros_files),
        "archivos_alumnos_descargados": len(downloaded_alumnos_files),
        "archivos_maestros_descargados": len(downloaded_maestros_files),
        "archivos_alumnos_movidos_a_procesados": archivos_movidos,
        "correos_etiquetados_procesados": correos_etiquetados,
        "correos_etiquetados_error": correos_error,
        "correos_sin_csv_adjunto": sin_csv,
        "errores_drive": errores_drive,
        "omitidos_por_duplicado": skipped,
        **resultado_proceso,
        **resultado_maestros,
    }


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
                })

    all_rows = deduplicate_training_rows(existing_rows + nuevos)

    write_csv(
        ALUMNOS_CAPACITACIONES_PATH,
        all_rows,
        ["id", "nombre", "correo", "curso", "modalidad", "fecha_actualizacion"],
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

    if GMAIL_MEET_MOVE_PROCESSED_FILES and processed_paths:
        move_files_to_processed_folder(processed_paths)

    return {
        "procesados_maestros": len(nuevos) + len(pendientes) + len(descartados),
        "validos_maestros": len(nuevos),
        "pendientes_maestros": len(pendientes),
        "descartados_maestros": len(descartados),
        "total_capacitaciones_maestros": len(all_rows),
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
    return bool(os.getenv("DATABASE_URL", "").strip())


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
                from database_postgres import leer_usuarios_reporte_postgres

                users = leer_usuarios_reporte_postgres(tipo)
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
                from database_postgres import leer_capacitaciones_reporte_postgres

                rows = leer_capacitaciones_reporte_postgres(tipo)
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


def build_report(
    rows: list[dict[str, str]],
    users: list[dict[str, str]],
    cursos_oficiales: list[str] | None = None,
    modalidades: list[str] | None = None,
    cursos_requeridos: int | None = None,
    ultima_actualizacion_path: Path = CAPACITACIONES_PATH,
) -> dict[str, Any]:
    cursos_oficiales = cursos_oficiales or CURSOS_OFICIALES
    modalidades = modalidades or MODALIDADES
    cursos_requeridos = cursos_requeridos or len(cursos_oficiales)

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
            "curso": row["curso"],
            "modalidad": row["modalidad"],
            "fecha_actualizacion": row["fecha_actualizacion"],
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
            "coincidencia": match_type,
        })

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
            }

        personas[persona_key]["cursos"].append(
            {
                "curso": resolved["curso"],
                "modalidad": resolved["modalidad"],
                "fecha_actualizacion": resolved["fecha_actualizacion"],
                "carrera": resolved.get("carrera", ""),
                "division": resolved.get("division", ""),
            }
        )

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
        persona["total_cursos"] = len(cursos_unicos)
        persona["completo"] = len(cursos_unicos) >= cursos_requeridos
        persona["pendientes"] = max(0, cursos_requeridos - len(cursos_unicos))
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
    cursos_1_y_2 = {norm(curso) for curso in cursos_oficiales[:2]}
    personas_con_cursos_1_y_2 = sum(
        1
        for persona in personas_lista
        if cursos_1_y_2.issubset({norm(curso["curso"]) for curso in persona["cursos"]})
    )

    personas_pendientes_con_avance = sum(1 for persona in personas_lista if not persona["completo"])

    if users:
        personas_pendientes = max(0, total_usuarios_esperados - personas_completas)
    else:
        personas_pendientes = personas_pendientes_con_avance

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
        "personas_pendientes": personas_pendientes,
        "personas_pendientes_con_avance": personas_pendientes_con_avance,
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
    rows, users = read_report_data("maestro")
    return jsonify(build_report(rows, users))


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
@login_required
def alumnos():
    return render_template("alumnos.html", **template_context())


@app.get("/api/alumnos/reporte")
@report_login_required
@login_required
def api_alumnos_reporte():
    rows, users = read_report_data("alumno")
    return jsonify(build_report(
        rows,
        users,
        cursos_oficiales=ALUMNOS_CURSOS_OFICIALES,
        modalidades=ALUMNOS_MODALIDADES,
        cursos_requeridos=1,
        ultima_actualizacion_path=ALUMNOS_CAPACITACIONES_PATH,
    ))


@app.get("/api/alumnos/datos")
@report_login_required
@login_required
def api_alumnos_datos():
    rows, users = read_report_data("alumno")
    return jsonify({
        "capacitaciones": rows,
        "usuarios": users,
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
    rows, users = read_report_data("maestro")
    reporte = build_report(rows, users)
    return render_template("admin.html", logged_in=True, error=None, reporte=reporte)


def validate_csv_headers(path: Path, required: set[str]) -> str | None:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            headers = {norm(header) for header in (reader.fieldnames or [])}
            missing = {header for header in required if norm(header) not in headers}
            if missing:
                return f"Faltan columnas en el CSV: {', '.join(sorted(missing))}"
    except UnicodeDecodeError:
        return "El CSV debe estar guardado en UTF-8."
    return None


def save_uploaded_csv(field_name: str, destination: Path, required_headers: set[str]) -> str | None:
    if field_name not in request.files:
        return "No se recibió ningún archivo."

    archivo = request.files[field_name]
    if not archivo.filename:
        return "Selecciona un archivo CSV."

    if not allowed_file(archivo.filename):
        return "Solo se permiten archivos .csv."

    filename = secure_filename(archivo.filename)
    temp_path = DATA_DIR / f"temp_{filename}"
    archivo.save(temp_path)

    error = validate_csv_headers(temp_path, required_headers)
    if error:
        temp_path.unlink(missing_ok=True)
        return error

    temp_path.replace(destination)
    return None


def wants_json_response() -> bool:
    return request.headers.get("X-Requested-With") == "fetch" or "application/json" in request.headers.get("Accept", "")


def admin_report_payload() -> dict[str, Any]:
    rows, users = read_report_data("maestro")
    return build_report(rows, users)


@app.post("/admin/upload/capacitaciones")
@report_login_required
@login_required
def upload_capacitaciones():
    required = {"id", "nombre", "carrera", "division", "curso", "modalidad", "fecha_actualizacion"}
    error = save_uploaded_csv("archivo", CAPACITACIONES_PATH, required)

    if not error:
        resultado_bd = sync_bd_safe()
    else:
        resultado_bd = None

    if wants_json_response():
        if error:
            return jsonify({"ok": False, "error": error}), 400
        return jsonify({"ok": True, "updated": "capacitaciones", "bd": resultado_bd, "reporte": admin_report_payload()})

    if error:
        rows, users = read_report_data("maestro")
        return render_template("admin.html", logged_in=True, error=error, reporte=build_report(rows, users))
    return redirect(url_for("admin_panel", updated="capacitaciones"))


@app.post("/admin/upload/usuarios")
@report_login_required
@login_required
def upload_usuarios():
    required = {"id", "nombre", "correo"}
    error = save_uploaded_csv("archivo", USUARIOS_PATH, required)

    if not error:
        resultado_bd = sync_bd_safe()
    else:
        resultado_bd = None

    if wants_json_response():
        if error:
            return jsonify({"ok": False, "error": error}), 400
        return jsonify({"ok": True, "updated": "usuarios", "bd": resultado_bd, "reporte": admin_report_payload()})

    if error:
        rows, users = read_report_data("maestro")
        return render_template("admin.html", logged_in=True, error=error, reporte=build_report(rows, users))
    return redirect(url_for("admin_panel", updated="usuarios"))


@app.post("/admin/upload/alumnos/usuarios")
@report_login_required
@login_required
def upload_alumnos_usuarios():
    required = {"id", "nombre", "correo"}
    error = save_uploaded_csv("archivo", ALUMNOS_USUARIOS_PATH, required)

    if not error:
        resultado_bd = sync_bd_safe()
    else:
        resultado_bd = None

    if wants_json_response():
        if error:
            return jsonify({"ok": False, "error": error}), 400
        rows_alumnos, users_alumnos = read_report_data("alumno")
        reporte_alumnos = build_report(
            rows_alumnos,
            users_alumnos,
            cursos_oficiales=ALUMNOS_CURSOS_OFICIALES,
            modalidades=ALUMNOS_MODALIDADES,
            cursos_requeridos=1,
            ultima_actualizacion_path=ALUMNOS_CAPACITACIONES_PATH,
        )
        return jsonify({"ok": True, "updated": "alumnos_usuarios", "bd": resultado_bd, "reporte_alumnos": reporte_alumnos})

    if error:
        rows, users = read_report_data("maestro")
        return render_template("admin.html", logged_in=True, error=error, reporte=build_report(rows, users))
    return redirect(url_for("admin_panel", updated="alumnos_usuarios"))


@app.post("/admin/upload/alumnos/meet")
@report_login_required
@login_required
def upload_alumnos_meet():
    if "archivo" not in request.files:
        error = "No se recibió ningún archivo."
        if wants_json_response():
            return jsonify({"ok": False, "error": error}), 400
        return redirect(url_for("admin_panel"))

    archivo = request.files["archivo"]
    if not archivo.filename:
        error = "Selecciona un archivo CSV de Meet."
        if wants_json_response():
            return jsonify({"ok": False, "error": error}), 400
        return redirect(url_for("admin_panel"))

    if not allowed_file(archivo.filename):
        error = "Solo se permiten archivos .csv."
        if wants_json_response():
            return jsonify({"ok": False, "error": error}), 400
        return redirect(url_for("admin_panel"))

    ALUMNOS_INSUMOS_DIR.mkdir(parents=True, exist_ok=True)
    filename = secure_filename(archivo.filename)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    saved_path = ALUMNOS_INSUMOS_DIR / f"{timestamp}_{filename}"
    archivo.save(saved_path)

    curso = clean(request.form.get("curso")) or ALUMNOS_CURSO_OFICIAL
    fecha_actualizacion = clean(request.form.get("fecha_actualizacion"))

    try:
        resultado = process_meet_csv(saved_path, curso=curso, fecha_actualizacion=fecha_actualizacion)
    except UnicodeDecodeError:
        error = "El CSV debe estar guardado en UTF-8."
        if wants_json_response():
            return jsonify({"ok": False, "error": error}), 400
        rows, users = read_report_data("maestro")
        return render_template("admin.html", logged_in=True, error=error, reporte=build_report(rows, users))

    resultado_bd = sync_bd_safe()
    rows_alumnos, users_alumnos = read_report_data("alumno")
    reporte_alumnos = build_report(
        rows_alumnos,
        users_alumnos,
        cursos_oficiales=ALUMNOS_CURSOS_OFICIALES,
        modalidades=ALUMNOS_MODALIDADES,
        cursos_requeridos=1,
        ultima_actualizacion_path=ALUMNOS_CAPACITACIONES_PATH,
    )

    if wants_json_response():
        return jsonify({
            "ok": True,
            "updated": "alumnos_meet",
            "resultado": resultado,
            "bd": resultado_bd,
            "reporte_alumnos": reporte_alumnos,
        })

    return redirect(url_for("admin_panel", updated="alumnos_meet"))



@app.post("/admin/alumnos/descargar-meet")
@report_login_required
@login_required
def descargar_meet_alumnos():
    curso = clean(request.form.get("curso")) or ALUMNOS_CURSO_OFICIAL
    query = clean(request.form.get("query")) or GMAIL_MEET_QUERY

    try:
        resultado = download_meet_reports_from_gmail(curso=curso, query=query)
    except MeetAutomationError as exc:
        error = str(exc)
        if wants_json_response():
            return jsonify({"ok": False, "error": error}), 400
        rows, users = read_report_data("maestro")
        return render_template("admin.html", logged_in=True, error=error, reporte=build_report(rows, users))
    except Exception as exc:
        error = f"No se pudo descargar Meet desde Gmail: {exc}"
        if wants_json_response():
            return jsonify({"ok": False, "error": error}), 400
        rows, users = read_report_data("maestro")
        return render_template("admin.html", logged_in=True, error=error, reporte=build_report(rows, users))

    try:
        resultado_bd = sincronizar_bd_desde_csv()
    except Exception as exc:
        resultado_bd = {
            "ok": False,
            "error": f"Meet se actualizó, pero no se pudo sincronizar la BD: {exc}",
        }

    rows_alumnos, users_alumnos = read_report_data("alumno")
    reporte_alumnos = build_report(
        rows_alumnos,
        users_alumnos,
        cursos_oficiales=ALUMNOS_CURSOS_OFICIALES,
        modalidades=ALUMNOS_MODALIDADES,
        cursos_requeridos=1,
        ultima_actualizacion_path=ALUMNOS_CAPACITACIONES_PATH,
    )

    if wants_json_response():
        return jsonify({
            "ok": True,
            "updated": "alumnos_meet_gmail",
            "resultado": resultado,
            "bd": resultado_bd,
            "reporte": admin_report_payload(),
            "reporte_alumnos": reporte_alumnos,
        })

    return redirect(url_for("admin_panel", updated="alumnos_meet_gmail"))

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


@app.get("/admin/download/alumnos/pendientes")
@report_login_required
@login_required
def download_alumnos_pendientes():
    headers = ["id", "nombre", "correo", "curso", "modalidad", "fecha_actualizacion", "duracion", "minutos_num", "motivo"]

    if not ALUMNOS_PENDIENTES_PATH.exists():
        return make_csv_response("alumnos_pendientes_revision.csv", [], headers)

    with ALUMNOS_PENDIENTES_PATH.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        rows = list(reader)

    return make_csv_response("alumnos_pendientes_revision.csv", rows, headers)


@app.get("/admin/download/alumnos/descartados")
@report_login_required
@login_required
def download_alumnos_descartados():
    headers = ["id", "nombre", "correo", "curso", "modalidad", "fecha_actualizacion", "duracion", "minutos_num", "motivo"]

    if not ALUMNOS_DESCARTADOS_PATH.exists():
        return make_csv_response("alumnos_descartados_menos_30_min.csv", [], headers)

    with ALUMNOS_DESCARTADOS_PATH.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        rows = list(reader)

    return make_csv_response("alumnos_descartados_menos_30_min.csv", rows, headers)



@app.get("/admin/download/maestros/meet-pendientes")
@report_login_required
@login_required
def download_maestros_meet_pendientes():
    headers = [
        "id", "nombre", "correo", "carrera", "division", "curso", "modalidad",
        "fecha_actualizacion", "duracion", "minutos_num", "archivo_origen", "hora_unio", "motivo",
    ]

    if not MAESTROS_PENDIENTES_MEET_PATH.exists():
        return make_csv_response("maestros_meet_pendientes_revision.csv", [], headers)

    with MAESTROS_PENDIENTES_MEET_PATH.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        rows = list(reader)

    return make_csv_response("maestros_meet_pendientes_revision.csv", rows, headers)


@app.get("/admin/download/maestros/meet-descartados")
@report_login_required
@login_required
def download_maestros_meet_descartados():
    headers = [
        "id", "nombre", "correo", "carrera", "division", "curso", "modalidad",
        "fecha_actualizacion", "duracion", "minutos_num", "archivo_origen", "hora_unio", "motivo",
    ]

    if not MAESTROS_DESCARTADOS_MEET_PATH.exists():
        return make_csv_response("maestros_meet_descartados_menos_30_min.csv", [], headers)

    with MAESTROS_DESCARTADOS_MEET_PATH.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        rows = list(reader)

    return make_csv_response("maestros_meet_descartados_menos_30_min.csv", rows, headers)


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


def sincronizar_bd_desde_csv() -> dict[str, Any]:
    from migrar_csv_a_bd import migrar_csv_a_bd

    resultado = migrar_csv_a_bd(reiniciar=True)
    backend = resultado.get("backend", "postgresql" if database_url_configurada() else "sqlite")

    if backend == "postgresql":
        destino = "DATABASE_URL"
    else:
        from database import DATABASE_PATH

        destino = str(DATABASE_PATH)

    return {
        "ok": True,
        "database_backend": backend,
        "database_path": destino,
        "resultado": resultado,
    }


def run_actualizar_meet_cli() -> int:
    ensure_runtime_directories()

    try:
        resultado = download_meet_reports_from_gmail()
    except MeetAutomationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: No se pudo actualizar Meet: {exc}", file=sys.stderr)
        return 1

    try:
        resultado_bd = sincronizar_bd_desde_csv()
    except Exception as exc:
        print(json.dumps(resultado, ensure_ascii=False, indent=2))
        print(f"ERROR: Meet se actualizó, pero no se pudo sincronizar la BD: {exc}", file=sys.stderr)
        return 1

    salida = {
        "meet": resultado,
        "bd": resultado_bd,
    }
    print(json.dumps(salida, ensure_ascii=False, indent=2))
    return 0


def run_migrar_bd_cli() -> int:
    ensure_runtime_directories()

    try:
        resultado_bd = sincronizar_bd_desde_csv()
    except Exception as exc:
        print(f"ERROR: No se pudo migrar a BD: {exc}", file=sys.stderr)
        return 1

    print(f"Base de datos generada/actualizada: {resultado_bd['database_path']}")
    print(json.dumps(resultado_bd["resultado"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    comando = sys.argv[1].strip().lower() if len(sys.argv) > 1 else ""

    if comando in {"actualizar-meet", "descargar-meet", "meet"}:
        raise SystemExit(run_actualizar_meet_cli())

    if comando in {"migrar-bd", "migrar-db", "bd", "db", "sincronizar-bd", "sync-bd", "sync-db"}:
        raise SystemExit(run_migrar_bd_cli())

    ensure_runtime_directories()
    app.run(debug=True)
