let reporteAlumnos = null;

const formatNumber = (value) => new Intl.NumberFormat("es-MX").format(Number(value || 0));
const normalizeText = (value) => String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();

function setText(id, value) {
    const element = document.getElementById(id);
    if (element) element.textContent = value;
}

function renderResumen(reporte) {
    setText("alumnosUltimaActualizacion", `Última actualización: ${reporte.ultima_actualizacion || "Sin datos"}`);
    setText("alumnosTotalPersonas", formatNumber(reporte.total_personas));
    setText("alumnosConAvance", formatNumber(reporte.personas_con_avance));
    setText("alumnosTotalRegistros", formatNumber(reporte.total_registros));
    setText("alumnosCompletos", formatNumber(reporte.personas_completas));
    setText("alumnosPendientes", formatNumber(reporte.personas_pendientes));
    setText("alumnosSinIniciar", formatNumber(reporte.usuarios_sin_iniciar));
}

function renderCurso(reporte) {
    const container = document.getElementById("alumnosCursoResumen");
    if (!container) return;

    const total = Number(reporte.total_personas || 0);
    const cursos = reporte.cursos_oficiales || [];
    const conteo = reporte.conteo_por_curso || {};

    container.innerHTML = cursos.map((curso) => {
        const completados = Number(conteo[curso] || 0);
        const porcentaje = total ? Math.round((completados / total) * 1000) / 10 : 0;
        return `
            <div class="summary-row progress-row">
                <div>
                    <strong>${curso}</strong>
                    <small>${formatNumber(completados)} de ${formatNumber(total)} alumnos</small>
                </div>
                <span>${porcentaje}%</span>
            </div>
        `;
    }).join("");
}

function renderResultados(query = "") {
    const container = document.getElementById("alumnosSearchResults");
    if (!container || !reporteAlumnos) return;

    const q = normalizeText(query);
    if (!q) {
        container.innerHTML = "";
        return;
    }

    const personas = (reporteAlumnos.personas || []).filter((persona) => {
        const texto = normalizeText(`${persona.id} ${persona.nombre} ${persona.correo}`);
        return texto.includes(q);
    }).slice(0, 20);

    if (!personas.length) {
        container.innerHTML = `<div class="panel"><p class="muted">No se encontraron alumnos.</p></div>`;
        return;
    }

    container.innerHTML = personas.map((persona) => {
        const cursos = persona.cursos || [];
        const rows = cursos.map((curso) => `
            <tr>
                <td>${curso.curso || ""}</td>
                <td>${curso.modalidad || ""}</td>
                <td>${curso.fecha_actualizacion || ""}</td>
            </tr>
        `).join("");

        return `
            <article class="panel result-card">
                <div class="result-header">
                    <div>
                        <h3>${persona.nombre || "Sin nombre"}</h3>
                        <p class="muted">${persona.correo || "Sin correo"}</p>
                    </div>
                    <span class="badge ${persona.completo ? "success" : "warning"}">
                        ${persona.completo ? "Completo" : `Pendiente: ${persona.pendientes}`}
                    </span>
                </div>
                <p><strong>Cursos completados:</strong> ${persona.total_cursos || 0} de ${(reporteAlumnos.cursos_oficiales || []).length}</p>
                <div class="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>Curso</th>
                                <th>Modalidad</th>
                                <th>Actualización</th>
                            </tr>
                        </thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
            </article>
        `;
    }).join("");
}

async function cargarReporteAlumnos() {
    const response = await fetch("/api/alumnos/reporte");
    if (!response.ok) throw new Error("No se pudo cargar el reporte de alumnos");
    reporteAlumnos = await response.json();
    renderResumen(reporteAlumnos);
    renderCurso(reporteAlumnos);
}

document.addEventListener("DOMContentLoaded", async () => {
    const input = document.getElementById("alumnosSearchInput");
    if (input) {
        input.addEventListener("input", () => renderResultados(input.value));
    }

    try {
        await cargarReporteAlumnos();
    } catch (error) {
        console.error(error);
        setText("alumnosUltimaActualizacion", "No se pudo cargar el reporte de alumnos.");
    }
});
