let reporte = null;
let modalidadActiva = "Presencial";
const registrosPorPagina = 10;
const paginasCurso = {};
const TOTAL_PARTICIPANTES_FALLBACK = 276;

const $ = (selector) => document.querySelector(selector);

const normalize = (text) =>
    String(text || "")
        .toLowerCase()
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .trim();

const pageKey = (modalidad, curso) => `${modalidad}::${curso}`;
function formatFecha(fecha) {
    if (!fecha) return "-";

    const texto = String(fecha).trim();

    if (texto.includes("/")) {
        return texto;
    }

    if (texto.includes("-")) {
        const partes = texto.split("-");
        if (partes.length === 3) {
            const [anio, mes, dia] = partes;
            return `${dia}/${mes}/${anio}`;
        }
    }

    return texto;
}

function getTotalParticipantesEsperados() {
    return Number(reporte?.total_usuarios_esperados) || Number(reporte?.total_personas) || TOTAL_PARTICIPANTES_FALLBACK;
}

function formatNumber(value) {
    return new Intl.NumberFormat("es-MX").format(Number(value) || 0);
}

function formatAvanceCurso(cantidad) {
    const totalEsperado = getTotalParticipantesEsperados();
    const porcentaje = totalEsperado > 0 ? (Number(cantidad || 0) / totalEsperado) * 100 : 0;
    return `${porcentaje.toFixed(1)}%`;
}

function detalleAvanceCurso(cantidad) {
    const totalEsperado = getTotalParticipantesEsperados();
    return `${formatNumber(cantidad)} de ${formatNumber(totalEsperado)}`;
}


async function loadReport() {
    const response = await fetch("/api/reporte", { cache: "no-store" });
    reporte = await response.json();
    renderReport();
}

function renderReport() {
    $("#totalRegistros").textContent = reporte.total_registros;
    $("#personasCursosUnoDos").textContent = reporte.personas_con_cursos_1_y_2 || 0;
    $("#ultimaActualizacion").textContent = `Última actualización: ${formatFecha(reporte.ultima_actualizacion)}`;

    renderPieCursosUnoDos();
    renderCursoResumen();
    renderTabs();
    renderModalidadContent();
    renderSearchResults();
}

function renderPieCursosUnoDos() {
    const completados = Number(reporte.personas_con_cursos_1_y_2 || 0);
    const totalEsperado = getTotalParticipantesEsperados();
    const pendientes = Math.max(totalEsperado - completados, 0);
    const porcentaje = totalEsperado > 0 ? (completados / totalEsperado) * 100 : 0;
    const grados = Math.max(0, Math.min(porcentaje, 100)) * 3.6;

    const pie = $("#pieCursosUnoDos");
    if (pie) {
        pie.style.setProperty("--pie-value", `${grados}deg`);
        pie.dataset.percent = `${porcentaje.toFixed(1)}%`;
    }

    $("#pieCompletados").textContent = formatNumber(completados);
    $("#piePendientes").textContent = formatNumber(pendientes);
}

function renderModalidadResumen() {
    const container = $("#modalidadResumen");
    container.innerHTML = reporte.modalidades
        .map((modalidad) => {
            const total = reporte.conteo_por_modalidad[modalidad] || 0;
            return `
                <div class="summary-row">
                    <span>${modalidad}</span>
                    <strong>${total}</strong>
                </div>
            `;
        })
        .join("");
}

function renderCursoResumen() {
    const container = $("#cursoResumen");
    const totalEsperado = getTotalParticipantesEsperados();

    container.innerHTML = reporte.cursos_oficiales
        .map((curso) => {
            const total = reporte.conteo_por_curso[curso] || 0;
            const porcentaje = totalEsperado > 0 ? (Number(total || 0) / totalEsperado) * 100 : 0;
            const detalle = detalleAvanceCurso(total);
            const porcentajeTexto = `${porcentaje.toFixed(1)}%`;
            const progreso = Math.max(0, Math.min(porcentaje, 100));
            return `
                <div class="summary-row summary-row-metric progress-row">
                    <div class="course-progress-info">
                        <span>${curso}</span>
                        <div class="progress-track" aria-label="${curso}: ${porcentajeTexto}">
                            <div class="progress-fill" style="width: ${progreso}%"></div>
                        </div>
                    </div>
                    <div class="metric-column" title="${detalle}">
                        <strong class="metric-value">${porcentajeTexto}</strong>
                        <small>${detalle}</small>
                    </div>
                </div>
            `;
        })
        .join("");
}

function renderTabs() {
    const container = $("#modalidadTabs");
    container.innerHTML = reporte.modalidades
        .map(
            (modalidad) => `
                <button class="tab ${modalidad === modalidadActiva ? "active" : ""}" data-modalidad="${modalidad}">
                    ${modalidad}
                </button>
            `
        )
        .join("");

    container.querySelectorAll(".tab").forEach((tab) => {
        tab.addEventListener("click", () => {
            modalidadActiva = tab.dataset.modalidad;
            renderTabs();
            renderModalidadContent();
        });
    });
}

function getCoursePage(modalidad, curso, totalPaginas) {
    const key = pageKey(modalidad, curso);
    const pagina = paginasCurso[key] || 1;
    return Math.min(Math.max(pagina, 1), Math.max(totalPaginas, 1));
}

function setCoursePage(modalidad, curso, pagina) {
    paginasCurso[pageKey(modalidad, curso)] = pagina;
    renderModalidadContent();
}

function csvValue(value) {
    return `"${String(value || "").replace(/"/g, '""')}"`;
}

function exportarTablaCurso(modalidad, curso) {
    const cursos = reporte.por_modalidad[modalidad] || {};
    const personas = cursos[curso] || [];
    const headers = ["nombre", "fecha_actualizacion"];
    const rows = personas.map((persona) => [persona.nombre || "Sin nombre", formatFecha(persona.fecha_actualizacion)]);
    const csv = "\ufeff" + [headers, ...rows].map((row) => row.map(csvValue).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const safeCurso = normalize(curso).replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "curso";
    const safeModalidad = normalize(modalidad).replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "modalidad";

    link.href = url;
    link.download = `${safeModalidad}-${safeCurso}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
}

function renderModalidadContent() {
    const container = $("#modalidadContent");
    const cursos = reporte.por_modalidad[modalidadActiva] || {};

    container.innerHTML = `
        <div class="courses-grid">
            ${reporte.cursos_oficiales
                .map((curso) => {
                    const personas = cursos[curso] || [];
                    const totalPaginas = Math.ceil(personas.length / registrosPorPagina) || 1;
                    const paginaActual = getCoursePage(modalidadActiva, curso, totalPaginas);
                    const inicio = (paginaActual - 1) * registrosPorPagina;
                    const visibles = personas.slice(inicio, inicio + registrosPorPagina);
                    const fin = personas.length ? Math.min(inicio + registrosPorPagina, personas.length) : 0;

                    return `
                        <article class="course-block compact-course">
                            <div class="course-header">
                                <h3>${curso}</h3>
                                <div class="course-actions">
                                    <span>${personas.length} registro${personas.length === 1 ? "" : "s"}</span>
                                    <button class="export-btn" type="button" data-curso="${curso}" data-modalidad="${modalidadActiva}" ${personas.length ? "" : "disabled"}>Exportar</button>
                                </div>
                            </div>
                            ${
                                personas.length
                                    ? `<div class="table-wrap course-table">
                                        <table>
                                            <thead>
                                                <tr>
                                                    <th>Nombre</th>
                                                    <th>Actualización</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                ${visibles
                                                    .map(
                                                        (persona) => `
                                                            <tr>
                                                                <td>${persona.nombre || "Sin nombre"}</td>
                                                                <td>${formatFecha(persona.fecha_actualizacion)}</td>
                                                            </tr>
                                                        `
                                                    )
                                                    .join("")}
                                            </tbody>
                                        </table>
                                    </div>
                                    <div class="pagination">
                                        <span>${inicio + 1}-${fin} de ${personas.length}</span>
                                        <div>
                                            <button class="pager-btn" data-curso="${curso}" data-page="${paginaActual - 1}" ${paginaActual === 1 ? "disabled" : ""}>Anterior</button>
                                            <button class="pager-btn" data-curso="${curso}" data-page="${paginaActual + 1}" ${paginaActual === totalPaginas ? "disabled" : ""}>Siguiente</button>
                                        </div>
                                    </div>`
                                    : `<p class="empty">Sin registros.</p>`
                            }
                        </article>
                    `;
                })
                .join("")}
        </div>
    `;

    container.querySelectorAll(".pager-btn").forEach((button) => {
        button.addEventListener("click", () => {
            setCoursePage(modalidadActiva, button.dataset.curso, Number(button.dataset.page));
        });
    });

    container.querySelectorAll(".export-btn").forEach((button) => {
        button.addEventListener("click", () => {
            exportarTablaCurso(button.dataset.modalidad, button.dataset.curso);
        });
    });
}

function renderSearchResults() {
    const query = normalize($("#searchInput").value);
    const container = $("#searchResults");

    if (!query) {
        container.innerHTML = "";
        return;
    }

    const results = reporte.personas.filter((persona) => {
        return (
            normalize(persona.nombre).includes(query) ||
            normalize(persona.id).includes(query) ||
            normalize(persona.correo).includes(query)
        );
    });

    if (!results.length) {
        container.innerHTML = `<p class="empty">No se encontraron resultados.</p>`;
        return;
    }

    container.innerHTML = results
        .map(
            (persona) => `
                <article class="person-card">
                    <div class="person-header">
                        <div>
                            <h3>${persona.nombre || "Sin nombre"}</h3>
                        </div>
                        <span class="status ${persona.completo ? "done" : "pending"}">
                            ${persona.completo ? "Completo" : `Pendiente: ${persona.pendientes}`}
                        </span>
                    </div>
                    <p><strong>Cursos completados:</strong> ${persona.total_cursos} de 6</p>
                    <div class="table-wrap">
                        <table>
                            <thead>
                                <tr>
                                    <th>Curso</th>
                                    <th>Modalidad</th>
                                    <th>Actualización</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${persona.cursos
                                    .map(
                                        (curso) => `
                                            <tr>
                                                <td>${curso.curso}</td>
                                                <td>${curso.modalidad}</td>
                                                <td>${formatFecha(curso.fecha_actualizacion)}</td>
                                            </tr>
                                        `
                                    )
                                    .join("")}
                            </tbody>
                        </table>
                    </div>
                </article>
            `
        )
        .join("");
}

document.addEventListener("DOMContentLoaded", () => {
    loadReport();
    $("#searchInput").addEventListener("input", renderSearchResults);
    $("#refreshBtn").addEventListener("click", loadReport);

});
