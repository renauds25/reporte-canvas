let reporteAlumnos = null;

const ALUMNOS_TODAS_CARRERAS = "__TODAS_CARRERAS__";
const alumnosRegistrosPorPagina = 20;
const ALUMNOS_TODOS_TIPOS = "__TODOS_TIPOS__";
let alumnosCarreraActiva = ALUMNOS_TODAS_CARRERAS;
let alumnosTipoActivo = ALUMNOS_TODOS_TIPOS;
let alumnosOrdenLista = "az";
let alumnosPaginaActual = 1;
let busquedaAlumnosResultados = [];

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

function cleanText(value) {
    const text = String(value ?? "").trim();
    const normalized = normalizeText(text);
    if (["", "null", "none", "nan", "n/a", "na", "sin dato", "sin datos"].includes(normalized)) {
        return "";
    }
    return text;
}

function getCarreraValue(value) {
    return cleanText(value) || "No disponible";
}

function getAlumnoKey(persona) {
    return String(persona?.id || persona?.correo || normalizeText(persona?.nombre) || "").trim();
}

function csvValue(value) {
    return `"${String(value ?? "").replace(/"/g, '""')}"`;
}

function formatFecha(fecha) {
    if (!fecha) return "";

    const texto = String(fecha).trim();
    if (!texto) return "";

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
        return new Date(anio, mes - 1, dia).getTime() || 0;
    }

    if (fechaSinHora.includes("-")) {
        const [anio, mes, dia] = fechaSinHora.split("-").map(Number);
        return new Date(anio, mes - 1, dia).getTime() || 0;
    }

    return 0;
}

function tipoCumplimientoLabel(tipo) {
    if (tipo === "revalidado") return "Revalidado";
    if (tipo === "nuevo") return "Dato nuevo";
    return "Pendiente";
}

function tipoAlumnoBadgeClass(tipo) {
    if (tipo === "revalidado") return "neutral";
    if (tipo === "nuevo") return "success";
    return "warning";
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

function getAlumnosPorKey() {
    const map = new Map();
    (reporteAlumnos?.personas || []).forEach((persona) => {
        const key = getAlumnoKey(persona);
        if (key) map.set(key, persona);
    });
    return map;
}

function getAlumnosBase() {
    const alumnosPorKey = getAlumnosPorKey();
    const usuarios = reporteAlumnos?.usuarios_lista || [];

    if (usuarios.length) {
        return usuarios.map((usuario) => {
            const persona = alumnosPorKey.get(getAlumnoKey(usuario));
            return {
                id: usuario.id || persona?.id || "",
                nombre: usuario.nombre || persona?.nombre || "Sin nombre",
                correo: usuario.correo || persona?.correo || "",
                carrera: getCarreraValue(usuario.carrera || persona?.carrera),
                division: usuario.division || persona?.division || "No disponible",
                cursos: persona?.cursos || [],
                total_cursos: persona?.total_cursos || 0,
                completo: Boolean(persona?.completo),
                tipo_cumplimiento: persona?.tipo_cumplimiento || "pendiente",
                pendientes: persona?.pendientes ?? 1,
                ultima_actualizacion: persona?.ultima_actualizacion || "",
            };
        });
    }

    return (reporteAlumnos?.personas || []).map((persona) => ({
        id: persona.id || "",
        nombre: persona.nombre || "Sin nombre",
        correo: persona.correo || "",
        carrera: getCarreraValue(persona.carrera),
        division: persona.division || "No disponible",
        cursos: persona.cursos || [],
        total_cursos: persona.total_cursos || 0,
        completo: Boolean(persona.completo),
        tipo_cumplimiento: persona.tipo_cumplimiento || "pendiente",
        pendientes: persona.pendientes ?? 1,
        ultima_actualizacion: persona.ultima_actualizacion || "",
    }));
}

function esCursoRevalidado(curso) {
    return Boolean(curso?.es_revalidacion) || normalizeText(curso?.modalidad) === "revalidado" || normalizeText(curso?.origen).includes("revalidacion");
}

function getRegistroPrincipalAlumno(alumno) {
    const cursos = alumno?.cursos || [];
    if (!cursos.length) return null;

    const nuevos = cursos.filter((curso) => !esCursoRevalidado(curso));
    const revalidados = cursos.filter(esCursoRevalidado);
    const candidatos = nuevos.length ? nuevos : revalidados;

    return [...candidatos].sort(
        (a, b) => parseFechaOrden(b.fecha_actualizacion) - parseFechaOrden(a.fecha_actualizacion)
    )[0] || null;
}

function crearFilaAlumno(alumno) {
    const registro = getRegistroPrincipalAlumno(alumno);
    const completado = Boolean(registro || alumno.completo);
    const fecha = registro?.fecha_actualizacion || alumno.ultima_actualizacion || "";
    const tipoCumplimiento = completado ? (registro && !esCursoRevalidado(registro) ? "nuevo" : alumno.tipo_cumplimiento || "revalidado") : "pendiente";

    return {
        id: alumno.id || "-",
        nombre: alumno.nombre || "Sin nombre",
        carrera: getCarreraValue(registro?.carrera || alumno.carrera),
        fecha: completado ? formatFecha(fecha) : "Pendiente",
        completado,
        tipo_cumplimiento: tipoCumplimiento,
        fecha_orden: parseFechaOrden(fecha),
    };
}

function getCarrerasAlumnosDisponibles() {
    const carreras = new Map();

    getAlumnosBase().forEach((alumno) => {
        const carrera = getCarreraValue(alumno.carrera);
        const key = normalizeText(carrera) || normalizeText("No disponible");
        if (!carreras.has(key)) carreras.set(key, carrera);
    });

    return Array.from(carreras.values()).sort((a, b) => {
        if (normalizeText(a) === "no disponible") return 1;
        if (normalizeText(b) === "no disponible") return -1;
        return a.localeCompare(b, "es");
    });
}

function renderAlumnosCareerFilter() {
    const select = document.getElementById("alumnosCareerSelect");
    if (!select || !reporteAlumnos) return;

    const carreras = getCarrerasAlumnosDisponibles();
    const carreraKeys = new Set(carreras.map((carrera) => normalizeText(carrera)));

    if (alumnosCarreraActiva !== ALUMNOS_TODAS_CARRERAS && !carreraKeys.has(alumnosCarreraActiva)) {
        alumnosCarreraActiva = ALUMNOS_TODAS_CARRERAS;
    }

    select.innerHTML = [
        `<option value="${ALUMNOS_TODAS_CARRERAS}">Todas</option>`,
        ...carreras.map((carrera) => {
            const key = normalizeText(carrera);
            return `<option value="${escapeHtml(key)}">${escapeHtml(carrera)}</option>`;
        }),
    ].join("");

    select.value = alumnosCarreraActiva;
}

function renderAlumnosTipoFilter() {
    const select = document.getElementById("alumnosTipoSelect");
    if (!select) return;

    const opciones = [
        [ALUMNOS_TODOS_TIPOS, "Todos"],
        ["revalidado", "Revalidado"],
        ["nuevo", "Dato nuevo"],
        ["pendiente", "Pendiente"],
    ];

    if (!opciones.some(([value]) => value === alumnosTipoActivo)) {
        alumnosTipoActivo = ALUMNOS_TODOS_TIPOS;
    }

    select.innerHTML = opciones
        .map(([value, label]) => `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`)
        .join("");
    select.value = alumnosTipoActivo;
}

function ordenarFilasAlumnos(filas) {
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
        revalidados: (a, b) => {
            const aRevalidado = a.tipo_cumplimiento === "revalidado";
            const bRevalidado = b.tipo_cumplimiento === "revalidado";
            if (aRevalidado !== bRevalidado) return aRevalidado ? -1 : 1;
            return a.nombre.localeCompare(b.nombre, "es");
        },
        nuevos: (a, b) => {
            const aNuevo = a.tipo_cumplimiento === "nuevo";
            const bNuevo = b.tipo_cumplimiento === "nuevo";
            if (aNuevo !== bNuevo) return aNuevo ? -1 : 1;
            if (a.fecha_orden !== b.fecha_orden) return b.fecha_orden - a.fecha_orden;
            return a.nombre.localeCompare(b.nombre, "es");
        },
        carrera: (a, b) => {
            const comparacionCarrera = getCarreraValue(a.carrera).localeCompare(getCarreraValue(b.carrera), "es");
            if (comparacionCarrera !== 0) return comparacionCarrera;
            return a.nombre.localeCompare(b.nombre, "es");
        },
        tipo: (a, b) => {
            const orden = { nuevo: 1, revalidado: 2, pendiente: 3 };
            const comparacionTipo = (orden[a.tipo_cumplimiento] || 9) - (orden[b.tipo_cumplimiento] || 9);
            if (comparacionTipo !== 0) return comparacionTipo;
            return a.nombre.localeCompare(b.nombre, "es");
        },
    };

    return [...filas].sort(ordenadores[alumnosOrdenLista] || ordenadores.az);
}

function getFilasAlumnos() {
    const filas = getAlumnosBase().map(crearFilaAlumno).filter((fila) => {
        const coincideCarrera = alumnosCarreraActiva === ALUMNOS_TODAS_CARRERAS
            || normalizeText(getCarreraValue(fila.carrera)) === alumnosCarreraActiva;
        const coincideTipo = alumnosTipoActivo === ALUMNOS_TODOS_TIPOS
            || fila.tipo_cumplimiento === alumnosTipoActivo;

        return coincideCarrera && coincideTipo;
    });

    return ordenarFilasAlumnos(filas);
}

function getAlumnosTotalPaginas(total) {
    return Math.ceil(total / alumnosRegistrosPorPagina) || 1;
}

function setAlumnosPagina(pagina) {
    const totalPaginas = getAlumnosTotalPaginas(getFilasAlumnos().length);
    alumnosPaginaActual = Math.min(Math.max(Number(pagina) || 1, 1), totalPaginas);
    renderListaAlumnos();
}

function exportarListaAlumnos() {
    const filas = getFilasAlumnos();
    const headers = ["id", "nombre", "carrera", "tipo", "fecha"];
    const rows = filas.map((fila) => [fila.id, fila.nombre, fila.carrera, tipoCumplimientoLabel(fila.tipo_cumplimiento), fila.fecha]);
    const csv = "\ufeff" + [headers, ...rows].map((row) => row.map(csvValue).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const carrera = alumnosCarreraActiva === ALUMNOS_TODAS_CARRERAS ? "todas" : alumnosCarreraActiva.replace(/[^a-z0-9]+/g, "-");
    const tipo = alumnosTipoActivo === ALUMNOS_TODOS_TIPOS ? "todos" : alumnosTipoActivo;

    link.href = url;
    link.download = `reporte-alumnos-${carrera}-${tipo}-${alumnosOrdenLista}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
}

function renderListaAlumnos() {
    const container = document.getElementById("alumnosListaContent");
    if (!container || !reporteAlumnos) return;

    const filas = getFilasAlumnos();
    const completados = filas.filter((fila) => fila.completado).length;
    const totalPaginas = getAlumnosTotalPaginas(filas.length);
    alumnosPaginaActual = Math.min(Math.max(alumnosPaginaActual, 1), totalPaginas);

    const inicio = (alumnosPaginaActual - 1) * alumnosRegistrosPorPagina;
    const visibles = filas.slice(inicio, inicio + alumnosRegistrosPorPagina);
    const fin = filas.length ? Math.min(inicio + alumnosRegistrosPorPagina, filas.length) : 0;

    container.innerHTML = `
        <article class="course-block selected-course-block alumnos-table-block">
            <div class="course-header">
                <div>
                    <h3>Alumnos</h3>
                    <p class="muted small-note">Lista general del curso de alumnos, con completados y pendientes.</p>
                </div>
                <div class="course-actions">
                    <span>${formatNumber(completados)} completado${completados === 1 ? "" : "s"}</span>
                    <button id="alumnosExportBtn" class="export-btn" type="button" ${filas.length ? "" : "disabled"}>Exportar</button>
                </div>
            </div>
            <div class="table-wrap selected-course-table alumnos-attendance-table">
                <table>
                    <thead>
                        <tr>
                            <th class="col-id">ID</th>
                            <th class="col-nombre">Nombre</th>
                            <th class="col-carrera-alumno">Carrera</th>
                            <th class="col-tipo-alumno">Tipo</th>
                            <th class="col-actualizacion">Fecha</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${visibles.length ? visibles.map((fila) => `
                            <tr>
                                <td class="col-id">${escapeHtml(fila.id)}</td>
                                <td class="col-nombre">${escapeHtml(fila.nombre)}</td>
                                <td class="col-carrera-alumno">${escapeHtml(fila.carrera)}</td>
                                <td class="col-tipo-alumno"><span class="badge ${tipoAlumnoBadgeClass(fila.tipo_cumplimiento)}">${escapeHtml(tipoCumplimientoLabel(fila.tipo_cumplimiento))}</span></td>
                                <td class="col-actualizacion">${fila.completado ? escapeHtml(fila.fecha) : `<span class="table-status pending">${escapeHtml(fila.fecha)}</span>`}</td>
                            </tr>
                        `).join("") : `<tr><td colspan="5" class="muted">No hay alumnos para los filtros seleccionados.</td></tr>`}
                    </tbody>
                </table>
            </div>
            <div class="pagination">
                <span>${filas.length ? `${inicio + 1}-${fin}` : "0"} de ${formatNumber(filas.length)}</span>
                <div>
                    <button class="pager-btn alumnos-pager-btn" data-page="${alumnosPaginaActual - 1}" ${alumnosPaginaActual === 1 ? "disabled" : ""}>Anterior</button>
                    <button class="pager-btn alumnos-pager-btn" data-page="${alumnosPaginaActual + 1}" ${alumnosPaginaActual === totalPaginas ? "disabled" : ""}>Siguiente</button>
                </div>
            </div>
        </article>
    `;

    container.querySelectorAll(".alumnos-pager-btn").forEach((button) => {
        button.addEventListener("click", () => setAlumnosPagina(button.dataset.page));
    });

    const exportBtn = document.getElementById("alumnosExportBtn");
    if (exportBtn) exportBtn.addEventListener("click", exportarListaAlumnos);
}

function renderResultados(query = "") {
    const container = document.getElementById("alumnosSearchResults");
    if (!container || !reporteAlumnos) return;

    const q = normalizeText(query);
    if (!q) {
        busquedaAlumnosResultados = [];
        container.innerHTML = "";
        return;
    }

    const personas = getAlumnosBase().filter((persona) => {
        const texto = normalizeText(`${persona.id} ${persona.nombre} ${persona.correo}`);
        return texto.includes(q);
    }).slice(0, 20);

    busquedaAlumnosResultados = personas;

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
                        <tbody>${rows || `<tr><td colspan="4">Sin cursos registrados.</td></tr>`}</tbody>
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
    renderAlumnosCareerFilter();
    renderAlumnosTipoFilter();
    renderListaAlumnos();
}

document.addEventListener("DOMContentLoaded", async () => {
    const input = document.getElementById("alumnosSearchInput");
    if (input) {
        input.addEventListener("input", () => renderResultados(input.value));
    }

    const careerSelect = document.getElementById("alumnosCareerSelect");
    if (careerSelect) {
        careerSelect.addEventListener("change", () => {
            alumnosCarreraActiva = careerSelect.value;
            alumnosPaginaActual = 1;
            renderListaAlumnos();
        });
    }

    const tipoSelect = document.getElementById("alumnosTipoSelect");
    if (tipoSelect) {
        tipoSelect.value = alumnosTipoActivo;
        tipoSelect.addEventListener("change", () => {
            alumnosTipoActivo = tipoSelect.value;
            alumnosPaginaActual = 1;
            renderListaAlumnos();
        });
    }

    const sortSelect = document.getElementById("alumnosSortSelect");
    if (sortSelect) {
        sortSelect.value = alumnosOrdenLista;
        sortSelect.addEventListener("change", () => {
            alumnosOrdenLista = sortSelect.value;
            alumnosPaginaActual = 1;
            renderListaAlumnos();
        });
    }

    try {
        await cargarReporteAlumnos();
    } catch (error) {
        console.error(error);
        setText("alumnosUltimaActualizacion", "No se pudo cargar el reporte de alumnos.");
    }
});
