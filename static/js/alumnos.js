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

function setHTML(id, value) {
    const element = document.getElementById(id);
    if (element) element.innerHTML = value;
}

function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function formatPercent(value) {
    const number = Number(value || 0);
    return `${Number.isInteger(number) ? number.toFixed(0) : number.toFixed(1)}%`;
}

function tipoCumplimientoLabel(tipo) {
    if (tipo === "revalidado") return "Revalidado";
    if (tipo === "nuevo") return "Dato nuevo";
    return "Pendiente";
}

function tipoCursoLabel(curso) {
    if (curso?.es_revalidacion) return "Revalidación";
    const origen = normalizeText(curso?.origen || "");
    if (origen.includes("api_directa")) return "Capacitación Meet";
    if (origen.includes("manual")) return "Carga manual";
    if (origen.includes("csv")) return "Carga CSV";
    return "Capacitación";
}

function badgeClass(persona) {
    if (!persona?.completo) return "warning";
    if (persona?.tipo_cumplimiento === "revalidado") return "neutral";
    return "success";
}

function renderResumen(reporte) {
    const total = Number(reporte.total_personas || 0);
    const revalidados = Number(reporte.alumnos_revalidados || 0);
    const nuevosCapacitados = Number(reporte.alumnos_nuevos_capacitados || 0);
    const nuevosEsperados = Number(reporte.alumnos_nuevos_esperados || 0);
    const nuevosPendientes = Number(reporte.alumnos_nuevos_pendientes || reporte.personas_pendientes || 0);
    const avanceTotal = Number(reporte.alumnos_porcentaje_cumplimiento || 0);
    const avanceRevalidado = Number(reporte.alumnos_porcentaje_revalidados || 0);
    const avanceNuevo = Number(reporte.alumnos_porcentaje_nuevos || 0);
    const cumplidos = Number(reporte.alumnos_cumplidos_total || reporte.personas_completas || 0);

    setText("alumnosUltimaActualizacion", `Última actualización: ${reporte.ultima_actualizacion || "Sin datos"}`);
    setText("alumnosTotalPersonas", formatNumber(total));
    setText("alumnosRevalidados", formatNumber(revalidados));
    setText("alumnosRevalidadosDetalle", `${formatPercent(avanceRevalidado)} del total`);
    setText("alumnosNuevosCapacitados", formatNumber(nuevosCapacitados));
    setText("alumnosNuevosDetalle", `${formatNumber(nuevosCapacitados)} de ${formatNumber(nuevosEsperados)} alumnos nuevos`);
    setText("alumnosAvanceTotal", formatPercent(avanceTotal));
    setHTML(
        "alumnosAvanceTotalDetalle",
        `${formatNumber(cumplidos)} de ${formatNumber(total)} alumnos · <span class="avance-percent">${formatPercent(avanceRevalidado)} revalidado</span> + <span class="avance-percent">${formatPercent(avanceNuevo)} nuevo</span>`
    );
    setText("alumnosPendientes", formatNumber(nuevosPendientes));
    setText("alumnosPendientesDetalle", "Alumnos nuevos pendientes de capacitación");
}

function renderCurso(reporte) {
    const container = document.getElementById("alumnosCursoResumen");
    if (!container) return;

    const total = Number(reporte.total_personas || 0);
    const cursos = reporte.cursos_oficiales || [];
    const conteo = reporte.conteo_por_curso || {};

    container.innerHTML = cursos.map((curso) => {
        const completados = Number(conteo[curso] || reporte.alumnos_cumplidos_total || 0);
        const porcentaje = total ? Math.round((completados / total) * 1000) / 10 : 0;
        const progreso = Math.max(0, Math.min(porcentaje, 100));
        const porcentajeTexto = formatPercent(porcentaje);
        const detalle = `${formatNumber(completados)} de ${formatNumber(total)} alumnos`;

        return `
            <div class="summary-row summary-row-metric progress-row">
                <div class="course-progress-info">
                    <span>${escapeHtml(curso)}</span>
                    <div class="progress-track" aria-label="${escapeHtml(curso)}: ${porcentajeTexto}">
                        <div class="progress-fill" style="width: ${progreso}%"></div>
                    </div>
                </div>
                <div class="metric-column" title="${escapeHtml(detalle)}">
                    <strong class="metric-value">${porcentajeTexto}</strong>
                    <small>${escapeHtml(detalle)}</small>
                </div>
            </div>
        `;
    }).join("");

    requestAnimationFrame(initProgressScrollAnimations);
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
                <td>${escapeHtml(curso.curso || "")}</td>
                <td>${escapeHtml(curso.modalidad || "")}</td>
                <td>${escapeHtml(tipoCursoLabel(curso))}</td>
                <td>${escapeHtml(curso.fecha_actualizacion || "")}</td>
            </tr>
        `).join("");
        const tipo = tipoCumplimientoLabel(persona.tipo_cumplimiento);
        const statusText = persona.completo ? tipo : `Pendiente: ${persona.pendientes}`;

        return `
            <article class="panel result-card">
                <div class="result-header">
                    <div>
                        <h3>${escapeHtml(persona.nombre || "Sin nombre")}</h3>
                        <p class="muted">${escapeHtml(persona.correo || "Sin correo")}</p>
                    </div>
                    <span class="badge ${badgeClass(persona)}">
                        ${escapeHtml(statusText)}
                    </span>
                </div>
                <p><strong>Cursos completados:</strong> ${formatNumber(persona.total_cursos || 0)} de ${(reporteAlumnos.cursos_oficiales || []).length}</p>
                <div class="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>Curso</th>
                                <th>Modalidad</th>
                                <th>Tipo</th>
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

function initProgressScrollAnimations() {
    const rows = document.querySelectorAll(".progress-row");

    if (!rows.length) return;

    rows.forEach(row => row.classList.remove("in-view"));

    if (!("IntersectionObserver" in window)) {
        rows.forEach(row => row.classList.add("in-view"));
        return;
    }

    const observer = new IntersectionObserver(
        entries => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add("in-view");
                    observer.unobserve(entry.target);
                }
            });
        },
        { threshold: 0.35 }
    );

    rows.forEach(row => observer.observe(row));
}

async function cargarReporteAlumnos() {
    const response = await fetch("/api/alumnos/reporte", { cache: "no-store" });
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
