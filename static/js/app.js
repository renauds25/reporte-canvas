let reporte = null;
let modalidadActiva = "Presencial";
const registrosPorPagina = 15;
const paginasCurso = {};

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

async function loadReport() {
    const response = await fetch("/api/reporte", { cache: "no-store" });
    reporte = await response.json();
    renderReport();
}

function renderReport() {
    $("#totalPersonas").textContent = reporte.personas_con_avance || reporte.total_personas;
    $("#totalRegistros").textContent = reporte.total_registros;
    $("#personasCompletas").textContent = reporte.personas_completas;
    $("#personasPendientes").textContent = reporte.personas_pendientes_con_avance ?? reporte.personas_pendientes;
    $("#ultimaActualizacion").textContent = `Última actualización: ${formatFecha(reporte.ultima_actualizacion)}`;

    renderModalidadResumen();
    renderCursoResumen();
    renderTabs();
    renderModalidadContent();
    renderSearchResults();
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
    container.innerHTML = reporte.cursos_oficiales
        .map((curso) => {
            const total = reporte.conteo_por_curso[curso] || 0;
            return `
                <div class="summary-row">
                    <span>${curso}</span>
                    <strong>${total}</strong>
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
                                <span>${personas.length} registro${personas.length === 1 ? "" : "s"}</span>
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
