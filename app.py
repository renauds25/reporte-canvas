from __future__ import annotations

import csv
import os
import unicodedata
from collections import defaultdict
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from authlib.integrations.flask_client import OAuth

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CAPACITACIONES_PATH = DATA_DIR / "capacitaciones.csv"
USUARIOS_PATH = DATA_DIR / "usuarios.csv"

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "hgjt8329")
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_ALLOWED_DOMAIN = os.environ.get("GOOGLE_ALLOWED_DOMAIN", "iest.edu.mx").lower().strip().lstrip("@")
ALLOWED_EXTENSIONS = {"csv"}

CURSOS_OFICIALES = [
    "CANVAS 1. INTRODUCCIÓN Y APUNTES.",
    "CANVAS 2. TAREAS Y SPEEDGRADER.",
    "CANVAS 3. GRUPOS (EQUIPOS).",
    "CANVAS 4. RÚBRICAS.",
    "CANVAS 5. FOROS DE DISCUSIÓN.",
    "CANVAS 6. EXÁMENES Y SPEEDGRADER.",
]

MODALIDADES = ["Presencial", "En línea", "A distancia"]

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cambia-esta-clave-en-produccion")
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

oauth = OAuth(app)
if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
    oauth.register(
        name="google",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin"))
        return view(*args, **kwargs)

    return wrapped_view


def google_login_enabled() -> bool:
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


def user_is_authenticated() -> bool:
    return not google_login_enabled() or bool(session.get("google_user"))


def google_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if user_is_authenticated():
            return view(*args, **kwargs)

        session["next_url"] = request.full_path if request.query_string else request.path
        return redirect(url_for("login"))

    return wrapped_view


def template_context() -> dict[str, Any]:
    return {
        "google_login_enabled": google_login_enabled(),
        "google_user": session.get("google_user"),
    }


def clean(value: Any) -> str:
    return str(value or "").strip()


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
        "correo": get_value(row, "correo", "Correo", "email", "mail", "e-mail"),
    }


def normalize_training_row(row: dict[str, str]) -> dict[str, str]:
    return {
        "id": get_value(row, "id", "ID", "matricula", "matrícula", "numero", "número"),
        "nombre": get_value(row, "nombre", "Nombre", "name", "participante"),
        "correo": get_value(row, "correo", "Correo", "email", "mail", "e-mail"),
        "curso": get_value(row, "curso", "Curso"),
        "modalidad": get_value(row, "modalidad", "Modalidad"),
        "fecha_actualizacion": get_value(row, "fecha_actualizacion", "Fecha_actualizacion", "fecha", "Fecha", "actualizacion", "actualización"),
    }


def read_users() -> list[dict[str, str]]:
    if not USUARIOS_PATH.exists():
        return []

    users: list[dict[str, str]] = []
    with USUARIOS_PATH.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for raw_row in reader:
            user = normalize_user_row(raw_row)
            if user["id"] or user["correo"] or user["nombre"]:
                users.append(user)
    return users


def read_capacitaciones() -> list[dict[str, str]]:
    if not CAPACITACIONES_PATH.exists():
        return []

    rows: list[dict[str, str]] = []
    with CAPACITACIONES_PATH.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for raw_row in reader:
            row = normalize_training_row(raw_row)
            has_identifier = row["id"] or row["correo"] or row["nombre"]
            if has_identifier and row["curso"] and row["modalidad"]:
                rows.append(row)

    return sorted(rows, key=lambda item: parse_date(item["fecha_actualizacion"]), reverse=True)


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


def build_report(rows: list[dict[str, str]], users: list[dict[str, str]]) -> dict[str, Any]:
    by_id, by_email, by_name = build_user_indexes(users)

    personas: dict[str, dict[str, Any]] = {}
    por_modalidad: dict[str, dict[str, list[dict[str, str]]]] = {
        modalidad: {curso: [] for curso in CURSOS_OFICIALES} for modalidad in MODALIDADES
    }
    conteo_por_modalidad = {modalidad: 0 for modalidad in MODALIDADES}
    conteo_por_curso_unico: dict[str, set[str]] = {curso: set() for curso in CURSOS_OFICIALES}
    registros_unicos_total: set[tuple[str, str]] = set()
    registros_sin_coincidencia: list[dict[str, str]] = []

    for row in rows:
        persona_key, master_user, match_type = resolve_person(row, by_id, by_email, by_name)

        resolved = {
            "id": master_user["id"] if master_user and master_user["id"] else row["id"],
            "nombre": master_user["nombre"] if master_user and master_user["nombre"] else row["nombre"],
            "correo": master_user["correo"] if master_user and master_user["correo"] else row["correo"],
            "curso": row["curso"],
            "modalidad": row["modalidad"],
            "fecha_actualizacion": row["fecha_actualizacion"],
            "coincidencia": match_type,
        }

        if match_type == "sin_coincidencia":
            registros_sin_coincidencia.append(resolved)

        if persona_key not in personas:
            personas[persona_key] = {
                "id": resolved["id"],
                "nombre": resolved["nombre"] or "Sin nombre",
                "correo": resolved["correo"],
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
            }
        )

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
        persona["completo"] = len(cursos_unicos) >= 6
        persona["pendientes"] = max(0, 6 - len(cursos_unicos))
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

    personas_pendientes_con_avance = sum(1 for persona in personas_lista if not persona["completo"])

    if users:
        personas_pendientes = max(0, total_usuarios_esperados - personas_completas)
    else:
        personas_pendientes = personas_pendientes_con_avance

    return {
        "cursos_oficiales": CURSOS_OFICIALES,
        "modalidades": MODALIDADES,
        "total_usuarios_esperados": total_usuarios_esperados,
        "total_personas": total_personas_reporte,
        "personas_con_avance": personas_con_avance,
        "usuarios_sin_iniciar": len(usuarios_sin_iniciar),
        "total_registros": len(registros_unicos_total),
        "total_registros_filas": len(rows),
        "personas_completas": personas_completas,
        "personas_pendientes": personas_pendientes,
        "personas_pendientes_con_avance": personas_pendientes_con_avance,
        "conteo_por_modalidad": conteo_por_modalidad,
        "conteo_por_curso": conteo_por_curso,
        "por_modalidad": por_modalidad,
        "personas": personas_lista,
        "usuarios_sin_iniciar_lista": usuarios_sin_iniciar,
        "registros_sin_coincidencia": registros_sin_coincidencia,
        "total_registros_sin_coincidencia": len(registros_sin_coincidencia),
        "ultima_actualizacion": rows[0]["fecha_actualizacion"] if rows else "Sin datos",
        "usa_base_maestra": bool(users),
    }


@app.get("/login")
def login():
    if not google_login_enabled():
        return redirect(url_for("index"))

    return render_template("login.html", error=None, allowed_domain=GOOGLE_ALLOWED_DOMAIN)


@app.get("/login/google")
def login_google():
    if not google_login_enabled():
        return redirect(url_for("index"))

    redirect_uri = url_for("auth_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@app.get("/auth/callback")
def auth_callback():
    if not google_login_enabled():
        return redirect(url_for("index"))

    try:
        token = oauth.google.authorize_access_token()
        userinfo = token.get("userinfo")
        if userinfo is None:
            userinfo = oauth.google.parse_id_token(token)
    except Exception:
        session.clear()
        return render_template(
            "login.html",
            error="No se pudo iniciar sesión con Google. Intenta nuevamente.",
            allowed_domain=GOOGLE_ALLOWED_DOMAIN,
        )

    email = clean(userinfo.get("email", "")).lower()
    domain = email.split("@")[-1] if "@" in email else ""

    if domain != GOOGLE_ALLOWED_DOMAIN:
        session.clear()
        return render_template(
            "login.html",
            error=f"Solo se permite el acceso con cuentas @{GOOGLE_ALLOWED_DOMAIN}.",
            allowed_domain=GOOGLE_ALLOWED_DOMAIN,
        )

    session["google_user"] = {
        "email": email,
        "name": clean(userinfo.get("name", "")),
        "picture": clean(userinfo.get("picture", "")),
    }

    next_url = session.pop("next_url", url_for("index"))
    return redirect(next_url or url_for("index"))


@app.route("/logout", methods=["GET", "POST"])
def logout_google():
    session.clear()
    return redirect(url_for("login") if google_login_enabled() else url_for("index"))


@app.get("/")
@google_required
def index():
    return render_template("index.html", **template_context())


@app.get("/api/reporte")
@google_required
def api_reporte():
    rows = read_capacitaciones()
    users = read_users()
    return jsonify(build_report(rows, users))


@app.route("/admin", methods=["GET", "POST"])
@google_required
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
@google_required
@login_required
def admin_panel():
    rows = read_capacitaciones()
    users = read_users()
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


@app.post("/admin/upload/capacitaciones")
@google_required
@login_required
def upload_capacitaciones():
    required = {"id", "nombre", "curso", "modalidad", "fecha_actualizacion"}
    error = save_uploaded_csv("archivo", CAPACITACIONES_PATH, required)
    if error:
        rows = read_capacitaciones()
        users = read_users()
        return render_template("admin.html", logged_in=True, error=error, reporte=build_report(rows, users))
    return redirect(url_for("admin_panel"))


@app.post("/admin/upload/usuarios")
@google_required
@login_required
def upload_usuarios():
    required = {"id", "nombre", "correo"}
    error = save_uploaded_csv("archivo", USUARIOS_PATH, required)
    if error:
        rows = read_capacitaciones()
        users = read_users()
        return render_template("admin.html", logged_in=True, error=error, reporte=build_report(rows, users))
    return redirect(url_for("admin_panel"))


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
@google_required
@login_required
def download_sin_coincidencia():
    reporte = build_report(read_capacitaciones(), read_users())
    headers = ["id", "nombre", "correo", "curso", "modalidad", "fecha_actualizacion", "coincidencia"]
    return make_csv_response("registros_sin_coincidencia.csv", reporte["registros_sin_coincidencia"], headers)


@app.get("/admin/download/sin-iniciar")
@google_required
@login_required
def download_sin_iniciar():
    reporte = build_report(read_capacitaciones(), read_users())
    headers = ["id", "nombre", "correo"]
    return make_csv_response("usuarios_sin_iniciar.csv", reporte["usuarios_sin_iniciar_lista"], headers)


@app.post("/admin/logout")
def logout():
    session.clear()
    return redirect(url_for("admin"))


if __name__ == "__main__":
    DATA_DIR.mkdir(exist_ok=True)
    app.run(debug=True)
