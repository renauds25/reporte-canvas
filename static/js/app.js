let reporte = null;

const TODOS_LOS_CURSOS = "__TODOS__";
const CURSOS_1_Y_2 = "__CANVAS_1_2__";
const TODAS_DIVISIONES = "__TODAS_DIVISIONES__";
const TODAS_CARRERAS = "__TODAS_CARRERAS__";
const DIVISIONES = [
    { key: "DCEA", label: "DCEA" },
    { key: "DCE", label: "DCE" },
    { key: "DH", label: "DH" },
    { key: "DCS", label: "DCS" },
    { key: "DFIIC", label: "DFIIC" },
    { key: "Otros", label: "Otros" },
    { key: TODAS_DIVISIONES, label: "Todas" },
];

let cursoActivo = CURSOS_1_Y_2;
let divisionActiva = TODAS_DIVISIONES;
let carreraActiva = TODAS_CARRERAS;
let ordenLista = "az";
const registrosPorPagina = 20;
const paginasCurso = {};
const TOTAL_PARTICIPANTES_FALLBACK = 276;
let busquedaResultadosActuales = [];

const $ = (selector) => document.querySelector(selector);

const normalize = (text) =>
    String(text || "")
        .toLowerCase()
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .trim();

const pageKey = (curso) => `${curso || CURSOS_1_Y_2}::${divisionActiva}::${carreraActiva}::${ordenLista}`;

function cleanText(text) {
    const value = String(text || "").trim();
    const normalized = value.toLowerCase();
    if (["null", "none", "nan", "n/a", "na", "sin dato", "sin datos"].includes(normalized)) {
        return "";
    }
    return value;
}

function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function getDivisionKey(value) {
    const raw = cleanText(value);
    const valueNorm = normalize(raw);

    if (!valueNorm || valueNorm === "no disponible") return "Otros";
    if (valueNorm.includes("formacion integral") || valueNorm.includes("identidad catolica")) return "DFIIC";
    if (valueNorm.includes("preparatoria")) return "Otros";
    if (valueNorm === "otros" || valueNorm === "otro") return "Otros";
    if (valueNorm === "dcea" || valueNorm.includes("economico") || valueNorm.includes("administrativa")) return "DCEA";
    if (valueNorm === "dce" || valueNorm.includes("exactas")) return "DCE";
    if (valueNorm === "dh" || valueNorm.includes("humanidades")) return "DH";
    if (valueNorm === "dcs" || valueNorm.includes("salud")) return "DCS";

    return "Otros";
}

function getCarreraValue(value) {
    const carrera = cleanText(value);
    return carrera || "No disponible";
}

function getCarreraAbreviada(value) {
    const carrera = getCarreraValue(value);
    const carreraNorm = normalize(carrera);

    if (!carreraNorm || carreraNorm === "no disponible") return "nd";

    const palabras = carrera
        .split(/\s+/)
        .map((word) => word.trim())
        .filter(Boolean)
        .filter((word) => !["de", "del", "la", "las", "el", "los", "y", "e", "en"].includes(normalize(word)));

    if (!palabras.length) return "nd";

    return palabras
        .map((word) => word[0])
        .join("")
        .toUpperCase()
        .slice(0, 8);
}

function renderCarreraCell(value) {
    const abreviada = getCarreraAbreviada(value);
    const tooltip = getCarreraValue(value);
    const extraClass = abreviada === "nd" ? " empty-badge" : "";
    return `<span class="career-badge${extraClass}" title="${escapeHtml(tooltip)}">${escapeHtml(abreviada)}</span>`;
}

function getDivisionValue(value) {
    const division = cleanText(value);
    return division || "No disponible";
}

function getDivisionAbreviada(value) {
    const division = getDivisionValue(value);
    const divisionNorm = normalize(division);
    const key = getDivisionKey(division);

    if (["DCEA", "DCE", "DH", "DCS"].includes(key)) return key;
    if (!divisionNorm || divisionNorm === "no disponible") return "nd";

    if (divisionNorm.includes("formacion integral") && divisionNorm.includes("identidad catolica")) return "DFIIC";
    if (divisionNorm.includes("formacion integral")) return "DFI";
    if (divisionNorm.includes("preparatoria")) return "DP";

    return division
        .split(/\s+/)
        .filter((word) => !["de", "del", "la", "las", "el", "los", "y", "e"].includes(normalize(word)))
        .map((word) => word[0])
        .join("")
        .toUpperCase()
        .slice(0, 6) || "nd";
}

function renderDivisionCell(value) {
    const abreviada = getDivisionAbreviada(value);
    const tooltip = getDivisionValue(value);
    const extraClass = abreviada === "nd" ? " empty-badge" : "";
    return `<span class="division-badge${extraClass}" title="${escapeHtml(tooltip)}">${escapeHtml(abreviada)}</span>`;
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
    if (!cursoActivo) cursoActivo = CURSOS_1_Y_2;
    renderReport();
}

function renderReport() {
    const ultimaActualizacion = $("#ultimaActualizacion");
    if (ultimaActualizacion) {
        ultimaActualizacion.textContent = `Última actualización: ${formatFecha(reporte.ultima_actualizacion)}`;
    }

    renderCursoResumen();
    renderDivisionTabs();
    renderTabs();
    renderCareerFilter();
    renderModalidadContent();
    renderSearchResults();
}

function renderCursoResumen() {
    const container = $("#cursoResumen");
    if (!container) return;

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
                        <span>${escapeHtml(curso)}</span>
                        <div class="progress-track" aria-label="${escapeHtml(curso)}: ${porcentajeTexto}">
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
            carreraActiva = TODAS_CARRERAS;
            paginasCurso[pageKey(cursoActivo)] = 1;
            renderDivisionTabs();
            renderCareerFilter();
            renderModalidadContent();
        });
    });
}

function getCourseDefinitions() {
    const oficiales = reporte?.cursos_oficiales || [];
    const curso1 = oficiales[0];
    const curso2 = oficiales[1];

    return [
        ...(curso1 && curso2 ? [{ key: CURSOS_1_Y_2, label: "CANVAS 1 + CANVAS 2", cursos: [curso1, curso2], muestraCurso: true }] : []),
        ...(curso1 ? [{ key: curso1, label: "CANVAS 1", cursos: [curso1], muestraCurso: false }] : []),
        ...(curso2 ? [{ key: curso2, label: "CANVAS 2", cursos: [curso2], muestraCurso: false }] : []),
        ...oficiales.slice(2).map((curso, index) => ({
            key: curso,
            label: `CANVAS ${index + 3}`,
            cursos: [curso],
            muestraCurso: false,
        })),
        { key: TODOS_LOS_CURSOS, label: "Todos", cursos: oficiales, muestraCurso: true },
    ];
}

function getCourseDefinition(cursoKey) {
    return getCourseDefinitions().find((item) => item.key === cursoKey) || getCourseDefinitions()[0];
}

function getCursoLabel(curso) {
    if (curso === TODOS_LOS_CURSOS) return "Todos";
    if (curso === CURSOS_1_Y_2) return "CANVAS 1 + CANVAS 2";

    const index = (reporte.cursos_oficiales || []).indexOf(curso);
    return index >= 0 ? `CANVAS ${index + 1}` : curso;
}

function renderTabs() {
    const container = $("#modalidadTabs");
    if (!container) return;

    const cursos = getCourseDefinitions();

    container.innerHTML = cursos
        .map((curso) => {
            return `
                <button class="tab ${curso.key === cursoActivo ? "active" : ""}" data-curso="${curso.key}">
                    ${curso.label}
                </button>
            `;
        })
        .join("");

    container.querySelectorAll(".tab").forEach((tab) => {
        tab.addEventListener("click", () => {
            cursoActivo = tab.dataset.curso;
            paginasCurso[pageKey(cursoActivo)] = 1;
            renderTabs();
            renderCareerFilter();
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

function getRegistrosCursoMaestro(maestro, curso) {
    const personasPorKey = getPersonasPorKey();
    const persona = personasPorKey.get(getPersonaKey(maestro));

    if (!persona) return [];

    const cursoNormalizado = normalize(curso);
    return (persona.cursos || []).filter((registro) => normalize(registro.curso) === cursoNormalizado);
}

function getRegistroCursoMaestro(maestro, curso) {
    const registros = getRegistrosCursoMaestro(maestro, curso);

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
        carrera: (a, b) => {
            const comparacionCarrera = getCarreraValue(a.carrera).localeCompare(getCarreraValue(b.carrera), "es");
            if (comparacionCarrera !== 0) return comparacionCarrera;
            return a.nombre.localeCompare(b.nombre, "es");
        },
    };

    return [...filas].sort(ordenadores[ordenLista] || ordenadores.az);
}


function getCarrerasDisponibles() {
    const carreras = new Map();

    getMaestrosBase().forEach((maestro) => {
        if (divisionActiva !== TODAS_DIVISIONES && getDivisionKey(maestro.division) !== divisionActiva) return;

        const carrera = getCarreraValue(maestro.carrera);
        const key = normalize(carrera) || normalize("No disponible");

        if (!carreras.has(key)) {
            carreras.set(key, carrera);
        }
    });

    return Array.from(carreras.values()).sort((a, b) => {
        if (normalize(a) === "no disponible") return 1;
        if (normalize(b) === "no disponible") return -1;
        return a.localeCompare(b, "es");
    });
}

function renderCareerFilter() {
    const select = $("#careerSelect");
    if (!select || !reporte) return;

    const carreras = getCarrerasDisponibles();
    const carreraKeys = new Set(carreras.map((carrera) => normalize(carrera)));

    if (carreraActiva !== TODAS_CARRERAS && !carreraKeys.has(carreraActiva)) {
        carreraActiva = TODAS_CARRERAS;
    }

    select.innerHTML = [
        `<option value="${TODAS_CARRERAS}">Todas</option>`,
        ...carreras.map((carrera) => {
            const key = normalize(carrera);
            return `<option value="${escapeHtml(key)}">${escapeHtml(carrera)}</option>`;
        }),
    ].join("");

    select.value = carreraActiva;
}

function aplicarFiltrosAcademicos(filas) {
    return filas.filter((fila) => {
        const division = getDivisionKey(fila.division);
        if (divisionActiva !== TODAS_DIVISIONES && division !== divisionActiva) return false;

        const carrera = normalize(getCarreraValue(fila.carrera));
        if (carreraActiva !== TODAS_CARRERAS && carrera !== carreraActiva) return false;

        return true;
    });
}

function crearFila(maestro, curso) {
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
}

function getFilasCurso(cursoKey) {
    const definition = getCourseDefinition(cursoKey);
    const filas = definition.cursos.flatMap((curso) => getMaestrosBase().map((maestro) => crearFila(maestro, curso)));
    return ordenarFilas(aplicarFiltrosAcademicos(filas));
}

function getFilasTodos() {
    return getFilasCurso(TODOS_LOS_CURSOS);
}

function getFilasExportacionCurso(cursoKey) {
    const definition = getCourseDefinition(cursoKey);
    const cursosPermitidos = new Set(definition.cursos.map((curso) => normalize(curso)));
    const registros = reporte.registros_detalle || [];

    if (!registros.length) {
        return getFilasCurso(cursoKey).filter((fila) => fila.completado);
    }

    const filas = registros
        .filter((registro) => cursosPermitidos.has(normalize(registro.curso)))
        .map((registro) => ({
            curso: registro.curso || "",
            id: registro.id || "-",
            nombre: registro.nombre || "Sin nombre",
            carrera: getCarreraValue(registro.carrera),
            division: registro.division || "No disponible",
            actualizacion: formatFecha(registro.fecha_actualizacion || ""),
            modalidad: registro.modalidad || "",
            completado: true,
            fecha_orden: parseFechaOrden(registro.fecha_actualizacion || ""),
        }));

    return ordenarFilas(aplicarFiltrosAcademicos(filas));
}

function exportarTablaCurso(cursoKey) {
    const definition = getCourseDefinition(cursoKey);
    const esTodos = cursoKey === TODOS_LOS_CURSOS;
    const muestraCurso = definition.muestraCurso || esTodos;
    const filas = getFilasExportacionCurso(cursoKey);
    const headers = muestraCurso
        ? ["curso", "id", "nombre", "carrera", "division", "fecha", "modalidad"]
        : ["id", "nombre", "carrera", "division", "fecha", "modalidad"];
    const rows = filas.map((fila) =>
        muestraCurso
            ? [fila.curso, fila.id, fila.nombre, fila.carrera, getDivisionValue(fila.division), fila.actualizacion, fila.modalidad]
            : [fila.id, fila.nombre, fila.carrera, getDivisionValue(fila.division), fila.actualizacion, fila.modalidad]
    );
    const csv = "\ufeff" + [headers, ...rows].map((row) => row.map(csvValue).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const safeCurso = normalize(definition.label).replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "curso";

    link.href = url;
    link.download = `${safeCurso}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
}

function renderModalidadContent() {
    const container = $("#modalidadContent");
    if (!container || !reporte) return;

    const curso = cursoActivo || CURSOS_1_Y_2;
    const definition = getCourseDefinition(curso);
    const esTodos = curso === TODOS_LOS_CURSOS;
    const muestraCurso = definition.muestraCurso || esTodos;
    const filas = getFilasCurso(curso);
    const completados = filas.filter((fila) => fila.completado).length;
    const totalPaginas = Math.ceil(filas.length / registrosPorPagina) || 1;
    const paginaActual = getCoursePage(curso, totalPaginas);
    const inicio = (paginaActual - 1) * registrosPorPagina;
    const visibles = filas.slice(inicio, inicio + registrosPorPagina);
    const fin = filas.length ? Math.min(inicio + registrosPorPagina, filas.length) : 0;
    const titulo = definition.label;
    const subtitulo = esTodos ? "Lista general de asistencia de todos los cursos." : "Lista de asistencia del curso seleccionado.";

    container.innerHTML = `
        <article class="course-block selected-course-block">
            <div class="course-header">
                <div>
                    <h3>${escapeHtml(titulo)}</h3>
                    <p class="muted small-note">${escapeHtml(subtitulo)}</p>
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
                            ${muestraCurso ? '<th class="col-curso">Curso</th>' : ""}
                            <th class="col-id">ID</th>
                            <th class="col-nombre">Nombre</th>
                            <th class="col-carrera">Carrera</th>
                            <th class="col-division">División</th>
                            <th class="col-actualizacion">Fecha</th>
                            <th class="col-modalidad">Modalidad</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${visibles
                            .map(
                                (fila) => `
                                    <tr>
                                        ${muestraCurso ? `<td class="col-curso">${escapeHtml(getCursoLabel(fila.curso))}</td>` : ""}
                                        <td class="col-id">${escapeHtml(fila.id)}</td>
                                        <td class="col-nombre">${escapeHtml(fila.nombre)}</td>
                                        <td class="col-carrera">${renderCarreraCell(fila.carrera)}</td>
                                        <td class="col-division">${renderDivisionCell(fila.division)}</td>
                                        <td class="col-actualizacion">${fila.completado ? escapeHtml(fila.actualizacion) : `<span class="table-status pending">${escapeHtml(fila.actualizacion)}</span>`}</td>
                                        <td class="col-modalidad">${fila.completado ? escapeHtml(fila.modalidad) : `<span class="table-status pending">${escapeHtml(fila.modalidad)}</span>`}</td>
                                    </tr>
                                `
                            )
                            .join("")}
                    </tbody>
                </table>
            </div>
            <div class="pagination">
                <span>${filas.length ? `${inicio + 1}-${fin}` : "0"} de ${filas.length}</span>
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

function exportarPersona(index) {
    const persona = busquedaResultadosActuales[Number(index)];
    if (!persona) return;

    const headers = ["id", "nombre", "carrera", "division", "curso", "modalidad", "fecha"];
    const cursos = persona.cursos || [];
    const rows = cursos.map((curso) => [
        persona.id || "",
        persona.nombre || "",
        getCarreraValue(curso.carrera || persona.carrera),
        getDivisionValue(curso.division || persona.division),
        curso.curso || "",
        curso.modalidad || "",
        formatFecha(curso.fecha_actualizacion || ""),
    ]);

    const csv = "\ufeff" + [headers, ...rows].map((row) => row.map(csvValue).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const safeName = normalize(persona.nombre || persona.id || "participante").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "participante";

    link.href = url;
    link.download = `${safeName}-cursos.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
}

function renderSearchResults() {
    const searchInput = $("#searchInput");
    const container = $("#searchResults");
    if (!searchInput || !container || !reporte) return;

    const query = normalize(searchInput.value);

    if (!query) {
        busquedaResultadosActuales = [];
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

    busquedaResultadosActuales = results;

    if (!results.length) {
        container.innerHTML = `<p class="empty">No se encontraron resultados.</p>`;
        return;
    }

    container.innerHTML = results
        .map(
            (persona, index) => `
                <article class="person-card">
                    <div class="person-header">
                        <div>
                            <h3>${escapeHtml(persona.nombre || "Sin nombre")}</h3>
                            <p class="muted small-note">${escapeHtml(getCarreraValue(persona.carrera))} · ${escapeHtml(getDivisionValue(persona.division))}</p>
                        </div>
                        <div class="person-actions">
                            <span class="status ${persona.completo ? "done" : "pending"}">
                                ${persona.completo ? "Completo" : `Número de cursos pendientes: ${persona.pendientes}`}
                            </span>
                            <button class="export-btn export-person-btn" type="button" data-index="${index}" ${(persona.cursos || []).length ? "" : "disabled"}>Exportar cursos</button>
                        </div>
                    </div>
                    <p><strong>Cursos completados:</strong> ${persona.total_cursos} de 6</p>
                    <div class="table-wrap">
                        <table>
                            <thead>
                                <tr>
                                    <th>Curso</th>
                                    <th>Modalidad</th>
                                    <th>Fecha</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${(persona.cursos || [])
                                    .map(
                                        (curso) => `
                                            <tr>
                                                <td>${escapeHtml(curso.curso)}</td>
                                                <td>${escapeHtml(curso.modalidad)}</td>
                                                <td>${escapeHtml(formatFecha(curso.fecha_actualizacion))}</td>
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

    container.querySelectorAll(".export-person-btn").forEach((button) => {
        button.addEventListener("click", () => exportarPersona(button.dataset.index));
    });
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
        sortSelect.value = ordenLista;
        sortSelect.addEventListener("change", () => {
            ordenLista = sortSelect.value;
            paginasCurso[pageKey(cursoActivo)] = 1;
            renderModalidadContent();
        });
    }

    const careerSelect = $("#careerSelect");
    if (careerSelect) {
        careerSelect.addEventListener("change", () => {
            carreraActiva = careerSelect.value;
            paginasCurso[pageKey(cursoActivo)] = 1;
            renderModalidadContent();
        });
    }
});
