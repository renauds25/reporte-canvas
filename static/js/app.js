let reporte = null;
const TODOS_LOS_CURSOS = "__TODOS__";
const TODAS_DIVISIONES = "__TODAS_DIVISIONES__";
const DIVISIONES = [
    { key: TODAS_DIVISIONES, label: "Todas" },
    { key: "DCEA", label: "DCEA" },
    { key: "DCE", label: "DCE" },
    { key: "DH", label: "DH" },
    { key: "DCS", label: "DCS" },
    { key: "Otros", label: "Otros" },
];
let cursoActivo = TODOS_LOS_CURSOS;
let divisionActiva = TODAS_DIVISIONES;
let ordenLista = "recientes";
const registrosPorPagina = 20;
const paginasCurso = {};
const TOTAL_PARTICIPANTES_FALLBACK = 276;

const $ = (selector) => document.querySelector(selector);

const normalize = (text) =>
    String(text || "")
        .toLowerCase()
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .trim();

const pageKey = (curso) => `${curso || TODOS_LOS_CURSOS}::${divisionActiva}::${ordenLista}`;

function cleanText(text) {
    const value = String(text || "").trim();
    const normalized = value.toLowerCase();
    if (["null", "none", "nan", "n/a", "na", "sin dato", "sin datos"].includes(normalized)) {
        return "";
    }
    return value;
}

function getDivisionKey(value) {
    const raw = cleanText(value);
    const valueNorm = normalize(raw);

    if (!valueNorm || valueNorm === "no disponible") return "Otros";
    if (
        valueNorm === "otros" ||
        valueNorm === "otro" ||
        valueNorm.includes("formacion integral") ||
        valueNorm.includes("identidad catolica") ||
        valueNorm.includes("preparatoria")
    ) return "Otros";
    if (valueNorm === "dcea" || valueNorm.includes("economico") || valueNorm.includes("administrativa")) return "DCEA";
    if (valueNorm === "dce" || valueNorm.includes("exactas")) return "DCE";
    if (valueNorm === "dh" || valueNorm.includes("humanidades")) return "DH";
    if (valueNorm === "dcs" || valueNorm.includes("salud")) return "DCS";

    return raw;
}

function getCarreraValue(value) {
    const carrera = cleanText(value);
    return carrera || "No disponible";
}

function getCarreraAbreviada(value) {
    const carrera = getCarreraValue(value);
    const carreraNorm = normalize(carrera);

    if (!carreraNorm || carreraNorm === "no disponible") return "ND";

    const palabras = carrera
        .split(/\s+/)
        .map((word) => word.trim())
        .filter(Boolean)
        .filter((word) => !["de", "del", "la", "las", "el", "los", "y", "e", "en"].includes(normalize(word)));

    if (!palabras.length) return "ND";

    return palabras
        .map((word) => word[0])
        .join("")
        .toUpperCase()
        .slice(0, 8);
}

function getCarreraTooltip(value) {
    const carrera = getCarreraValue(value);
    return carrera || "No disponible";
}

function renderCarreraCell(value) {
    const abreviada = getCarreraAbreviada(value);
    const tooltip = getCarreraTooltip(value);
    return `<span class="career-badge" title="${tooltip}">${abreviada}</span>`;
}

function getDivisionValue(value) {
    const division = cleanText(value);
    return division || "No disponible";
}

function getDivisionLabel(key) {
    const match = DIVISIONES.find((division) => division.key === key);
    return match ? match.label : key;
}

function getDivisionAbreviada(value) {
    const division = getDivisionValue(value);
    const divisionNorm = normalize(division);
    const key = getDivisionKey(division);

    if (["DCEA", "DCE", "DH", "DCS"].includes(key)) return key;
    if (!divisionNorm || divisionNorm === "no disponible") return "ND";

    if (divisionNorm.includes("formacion integral") && divisionNorm.includes("identidad catolica")) return "DFIIC";
    if (divisionNorm.includes("formacion integral")) return "DFI";
    if (divisionNorm.includes("preparatoria")) return "DP";

    return division
        .split(/\s+/)
        .filter((word) => !["de", "del", "la", "las", "el", "los", "y", "e"].includes(normalize(word)))
        .map((word) => word[0])
        .join("")
        .toUpperCase()
        .slice(0, 6) || "ND";
}

function getDivisionTooltip(value) {
    const division = getDivisionValue(value);
    return division || "No disponible";
}

function renderDivisionCell(value) {
    const abreviada = getDivisionAbreviada(value);
    const tooltip = getDivisionTooltip(value);
    return `<span class="division-badge" title="${tooltip}">${abreviada}</span>`;
}

function formatFecha(fecha) {
    if (!fecha) return "-";

    const texto = String(fecha).trim();

    if (texto.includes("/") && texto.includes(":")) return texto;
    if (texto.includes("/") && !texto.includes("-")) return texto;

    if (texto.includes("-")) {
        const partes = texto.split("-");
        if (partes.length === 3) {
            const [anio, mes, dia] = partes;
            return `${dia}/${mes}/${anio}`;
        }
    }

    return texto;
}

function parseFechaOrden(fecha) {
    if (!fecha) return 0;

    const texto = String(fecha).trim();
    const fechaSinHora = texto.split(" ")[0];

    if (fechaSinHora.includes("/")) {
        const [dia, mes, anio] = fechaSinHora.split("/").map(Number);
        return new Date(anio, mes - 1, dia).getTime();
    }

    if (fechaSinHora.includes("-")) {
        const [anio, mes, dia] = fechaSinHora.split("-").map(Number);
        return new Date(anio, mes - 1, dia).getTime();
    }

    return 0;
}

function getTotalParticipantesEsperados() {
    return Number(reporte?.total_usuarios_esperados) || Number(reporte?.total_personas) || TOTAL_PARTICIPANTES_FALLBACK;
}

function formatNumber(value) {
    return new Intl.NumberFormat("es-MX").format(Number(value) || 0);
}

function detalleAvanceCurso(cantidad) {
    const totalEsperado = getTotalParticipantesEsperados();
    return `${formatNumber(cantidad)} de ${formatNumber(totalEsperado)}`;
}

async function loadReport() {
    const response = await fetch("/api/reporte", { cache: "no-store" });
    reporte = await response.json();
    if (!cursoActivo) cursoActivo = TODOS_LOS_CURSOS;
    renderReport();
}

function renderReport() {
    $("#ultimaActualizacion").textContent = `Última actualización: ${formatFecha(reporte.ultima_actualizacion)}`;

    renderPieCursosUnoDos();
    renderCursoResumen();
    renderDivisionTabs();
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

function renderDivisionTabs() {
    const container = $("#divisionTabs");
    if (!container) return;

    container.innerHTML = DIVISIONES.map(
        (division) => `
            <button class="tab ${division.key === divisionActiva ? "active" : ""}" data-division="${division.key}">
                ${division.label}
            </button>
        `
    ).join("");

    container.querySelectorAll(".tab").forEach((tab) => {
        tab.addEventListener("click", () => {
            divisionActiva = tab.dataset.division;
            paginasCurso[pageKey(cursoActivo)] = 1;
            renderDivisionTabs();
                    renderModalidadContent();
        });
    });
}


function getCursoLabel(curso) {
    if (curso === TODOS_LOS_CURSOS) return "Todos";

    const index = (reporte.cursos_oficiales || []).indexOf(curso);
    return index >= 0 ? `CANVAS ${index + 1}` : curso;
}

function renderTabs() {
    const container = $("#modalidadTabs");
    const cursos = [TODOS_LOS_CURSOS, ...(reporte.cursos_oficiales || [])];

    container.innerHTML = cursos
        .map((curso) => {
            return `
                <button class="tab ${curso === cursoActivo ? "active" : ""}" data-curso="${curso}">
                    ${getCursoLabel(curso)}
                </button>
            `;
        })
        .join("");

    container.querySelectorAll(".tab").forEach((tab) => {
        tab.addEventListener("click", () => {
            cursoActivo = tab.dataset.curso;
            paginasCurso[pageKey(cursoActivo)] = 1;
            renderTabs();
            renderModalidadContent();
        });
    });
}

function getCoursePage(curso, totalPaginas) {
    const key = pageKey(curso);
    const pagina = paginasCurso[key] || 1;
    return Math.min(Math.max(pagina, 1), Math.max(totalPaginas, 1));
}

function setCoursePage(curso, pagina) {
    paginasCurso[pageKey(curso)] = pagina;
    renderModalidadContent();
}

function csvValue(value) {
    return `"${String(value || "").replace(/"/g, '""')}"`;
}

function getPersonaKey(persona) {
    return String(persona.id || persona.correo || normalize(persona.nombre) || "").trim();
}

function getPersonasPorKey() {
    const map = new Map();
    (reporte.personas || []).forEach((persona) => {
        const key = getPersonaKey(persona);
        if (key) map.set(key, persona);
    });
    return map;
}

function getMaestrosBase() {
    const personasPorKey = getPersonasPorKey();
    const usuarios = reporte.usuarios_lista || [];

    if (usuarios.length) {
        return usuarios.map((usuario) => {
            const persona = personasPorKey.get(getPersonaKey(usuario));
            return {
                id: usuario.id || persona?.id || "",
                nombre: usuario.nombre || persona?.nombre || "Sin nombre",
                correo: usuario.correo || persona?.correo || "",
                carrera: usuario.carrera || persona?.carrera || "No disponible",
                division: usuario.division || persona?.division || "No disponible",
            };
        });
    }

    return (reporte.personas || []).map((persona) => ({
        id: persona.id || "",
        nombre: persona.nombre || "Sin nombre",
        correo: persona.correo || "",
        carrera: persona.carrera || "No disponible",
        division: persona.division || "No disponible",
    }));
}

function getRegistroCursoMaestro(maestro, curso) {
    const personasPorKey = getPersonasPorKey();
    const persona = personasPorKey.get(getPersonaKey(maestro));

    if (!persona) return null;

    const cursoNormalizado = normalize(curso);
    const registros = (persona.cursos || []).filter(
        (registro) => normalize(registro.curso) === cursoNormalizado
    );

    if (!registros.length) return null;

    return registros.sort(
        (a, b) => parseFechaOrden(b.fecha_actualizacion) - parseFechaOrden(a.fecha_actualizacion)
    )[0];
}

function ordenarFilas(filas) {
    const ordenadores = {
        recientes: (a, b) => {
            if (a.completado !== b.completado) return a.completado ? -1 : 1;
            if (a.fecha_orden !== b.fecha_orden) return b.fecha_orden - a.fecha_orden;
            return a.nombre.localeCompare(b.nombre, "es");
        },

        id: (a, b) => {
            const idA = Number(String(a.id || "").replace(/\D/g, ""));
            const idB = Number(String(b.id || "").replace(/\D/g, ""));

            if (idA && idB) return idA - idB;
            return String(a.id || "").localeCompare(String(b.id || ""), "es", { numeric: true });
        },

        id_desc: (a, b) => {
            const idA = Number(String(a.id || "").replace(/\D/g, ""));
            const idB = Number(String(b.id || "").replace(/\D/g, ""));

            if (idA && idB) return idB - idA;
            return String(b.id || "").localeCompare(String(a.id || ""), "es", { numeric: true });
        },

        az: (a, b) => a.nombre.localeCompare(b.nombre, "es"),

        za: (a, b) => b.nombre.localeCompare(a.nombre, "es"),

        pendientes: (a, b) => {
            if (a.completado !== b.completado) return a.completado ? 1 : -1;
            return a.nombre.localeCompare(b.nombre, "es");
        },

        completados: (a, b) => {
            if (a.completado !== b.completado) return a.completado ? -1 : 1;
            if (a.fecha_orden !== b.fecha_orden) return b.fecha_orden - a.fecha_orden;
            return a.nombre.localeCompare(b.nombre, "es");
        },

        modalidad: (a, b) => {
            const modalidadA = a.completado ? a.modalidad : "zz Pendiente";
            const modalidadB = b.completado ? b.modalidad : "zz Pendiente";
            const comparacionModalidad = modalidadA.localeCompare(modalidadB, "es");
            if (comparacionModalidad !== 0) return comparacionModalidad;
            return a.nombre.localeCompare(b.nombre, "es");
        },
        division: (a, b) => {
            const comparacionDivision = getDivisionKey(a.division).localeCompare(getDivisionKey(b.division), "es");
            if (comparacionDivision !== 0) return comparacionDivision;
            return a.nombre.localeCompare(b.nombre, "es");
        },
    };

    return [...filas].sort(ordenadores[ordenLista] || ordenadores.recientes);
}

function aplicarFiltrosAcademicos(filas) {
    return filas.filter((fila) => {
        const division = getDivisionKey(fila.division);
        const carrera = getCarreraValue(fila.carrera);

        if (divisionActiva !== TODAS_DIVISIONES && division !== divisionActiva) return false;

        return true;
    });
}

function getFilasCurso(curso) {
    const filas = getMaestrosBase().map((maestro) => {
        const registro = getRegistroCursoMaestro(maestro, curso);
        const completado = Boolean(registro);
        const fecha = registro?.fecha_actualizacion || "";

        return {
            id: maestro.id || "-",
            nombre: maestro.nombre || "Sin nombre",
            carrera: getCarreraValue(registro?.carrera || maestro.carrera),
            division: registro?.division || maestro.division || "No disponible",
            actualizacion: completado ? formatFecha(fecha) : "Pendiente",
            modalidad: completado ? registro.modalidad : "Pendiente",
            completado,
            fecha_orden: parseFechaOrden(fecha),
        };
    });

    return ordenarFilas(aplicarFiltrosAcademicos(filas));
}

function getFilasTodos() {
    const filas = (reporte.cursos_oficiales || []).flatMap((curso) =>
        getMaestrosBase().map((maestro) => {
            const registro = getRegistroCursoMaestro(maestro, curso);
            const completado = Boolean(registro);
            const fecha = registro?.fecha_actualizacion || "";

            return {
                curso,
                id: maestro.id || "-",
                nombre: maestro.nombre || "Sin nombre",
                carrera: getCarreraValue(registro?.carrera || maestro.carrera),
                division: registro?.division || maestro.division || "No disponible",
                actualizacion: completado ? formatFecha(fecha) : "Pendiente",
                modalidad: completado ? registro.modalidad : "Pendiente",
                completado,
                fecha_orden: parseFechaOrden(fecha),
            };
        })
    );

    return ordenarFilas(aplicarFiltrosAcademicos(filas));
}

function exportarTablaCurso(curso) {
    const esTodos = curso === TODOS_LOS_CURSOS;
    const filas = esTodos ? getFilasTodos() : getFilasCurso(curso);
    const headers = esTodos
        ? ["curso", "id", "nombre", "carrera", "division", "actualizacion", "modalidad"]
        : ["id", "nombre", "carrera", "division", "actualizacion", "modalidad"];
    const rows = filas.map((fila) =>
        esTodos
            ? [fila.curso, fila.id, fila.nombre, fila.carrera, getDivisionValue(fila.division), fila.actualizacion, fila.modalidad]
            : [fila.id, fila.nombre, fila.carrera, getDivisionValue(fila.division), fila.actualizacion, fila.modalidad]
    );
    const csv = "\ufeff" + [headers, ...rows].map((row) => row.map(csvValue).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const safeCurso = esTodos
        ? "todos-los-cursos"
        : normalize(curso).replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "curso";

    link.href = url;
    link.download = `${safeCurso}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
}

function renderModalidadContent() {
    const container = $("#modalidadContent");
    const curso = cursoActivo || TODOS_LOS_CURSOS;
    const esTodos = curso === TODOS_LOS_CURSOS;
    const filas = esTodos ? getFilasTodos() : getFilasCurso(curso);
    const completados = filas.filter((fila) => fila.completado).length;
    const totalPaginas = Math.ceil(filas.length / registrosPorPagina) || 1;
    const paginaActual = getCoursePage(curso, totalPaginas);
    const inicio = (paginaActual - 1) * registrosPorPagina;
    const visibles = filas.slice(inicio, inicio + registrosPorPagina);
    const fin = filas.length ? Math.min(inicio + registrosPorPagina, filas.length) : 0;
    const titulo = esTodos ? "Todos los cursos" : curso;
    const subtitulo = esTodos ? "Lista general de asistencia de todos los cursos." : "Lista de asistencia del curso seleccionado.";

    container.innerHTML = `
        <article class="course-block selected-course-block">
            <div class="course-header">
                <div>
                    <h3>${titulo}</h3>
                    <p class="muted small-note">${subtitulo}</p>
                </div>
                <div class="course-actions">
                    <span>${completados} completado${completados === 1 ? "" : "s"}</span>
                    <button class="export-btn" type="button" data-curso="${curso}" ${filas.length ? "" : "disabled"}>Exportar</button>
                </div>
            </div>
            <div class="table-wrap course-table selected-course-table">
                <table>
                    <thead>
                        <tr>
                            ${esTodos ? '<th class="col-curso">Curso</th>' : ""}
                            <th class="col-id">ID</th>
                            <th class="col-nombre">Nombre</th>
                            <th class="col-carrera">Carrera</th>
                            <th class="col-division">División</th>
                            <th class="col-actualizacion">Actualización</th>
                            <th class="col-modalidad">Modalidad</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${visibles
                            .map(
                                (fila) => `
                                    <tr>
                                        ${esTodos ? `<td class="col-curso">${getCursoLabel(fila.curso)}</td>` : ""}
                                        <td class="col-id">${fila.id}</td>
                                        <td class="col-nombre">${fila.nombre}</td>
                                        <td class="col-carrera">${renderCarreraCell(fila.carrera)}</td>
                                        <td class="col-division">${renderDivisionCell(fila.division)}</td>
                                        <td class="col-actualizacion">${fila.completado ? fila.actualizacion : `<span class="table-status pending">${fila.actualizacion}</span>`}</td>
                                        <td class="col-modalidad">${fila.completado ? fila.modalidad : `<span class="table-status pending">${fila.modalidad}</span>`}</td>
                                    </tr>
                                `
                            )
                            .join("")}
                    </tbody>
                </table>
            </div>
            <div class="pagination">
                <span>${inicio + 1}-${fin} de ${filas.length}</span>
                <div>
                    <button class="pager-btn" data-page="${paginaActual - 1}" ${paginaActual === 1 ? "disabled" : ""}>Anterior</button>
                    <button class="pager-btn" data-page="${paginaActual + 1}" ${paginaActual === totalPaginas ? "disabled" : ""}>Siguiente</button>
                </div>
            </div>
        </article>
    `;

    container.querySelectorAll(".pager-btn").forEach((button) => {
        button.addEventListener("click", () => {
            setCoursePage(curso, Number(button.dataset.page));
        });
    });

    container.querySelectorAll(".export-btn").forEach((button) => {
        button.addEventListener("click", () => {
            exportarTablaCurso(button.dataset.curso);
        });
    });
}

function getPersonasBusqueda() {
    const personasPorKey = getPersonasPorKey();
    return getMaestrosBase().map((maestro) => {
        const persona = personasPorKey.get(getPersonaKey(maestro));
        if (persona) return persona;

        return {
            id: maestro.id || "",
            nombre: maestro.nombre || "Sin nombre",
            correo: maestro.correo || "",
            carrera: maestro.carrera || "No disponible",
            division: maestro.division || "No disponible",
            cursos: [],
            total_cursos: 0,
            completo: false,
            pendientes: 6,
        };
    });
}

function renderSearchResults() {
    const query = normalize($("#searchInput").value);
    const container = $("#searchResults");

    if (!query) {
        container.innerHTML = "";
        return;
    }

    const results = getPersonasBusqueda().filter((persona) => {
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
                            <p class="muted small-note">${getCarreraValue(persona.carrera)} · ${getDivisionValue(persona.division)}</p>
                        </div>
                        <span class="status ${persona.completo ? "done" : "pending"}">
                            ${persona.completo ? "Completo" : `Número de cursos pendientes: ${persona.pendientes}`}
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
                                ${(persona.cursos || [])
                                    .map(
                                        (curso) => `
                                            <tr>
                                                <td>${curso.curso}</td>
                                                <td>${curso.modalidad}</td>
                                                <td>${formatFecha(curso.fecha_actualizacion)}</td>
                                            </tr>
                                        `
                                    )
                                    .join("") || `<tr><td colspan="3">Sin cursos registrados.</td></tr>`}
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

    const searchInput = $("#searchInput");
    if (searchInput) {
        searchInput.addEventListener("input", renderSearchResults);
    }

    const refreshBtn = $("#refreshBtn");
    if (refreshBtn) {
        refreshBtn.addEventListener("click", loadReport);
    }

    const sortSelect = $("#sortSelect");
    if (sortSelect) {
        sortSelect.addEventListener("change", () => {
            ordenLista = sortSelect.value;
            paginasCurso[pageKey(cursoActivo)] = 1;
            renderModalidadContent();
        });
    }
});
