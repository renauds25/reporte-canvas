const ENDPOINT_API = "https://reporte-canvas.onrender.com/api/meet/asistencia";

// Cambia este valor según la cuenta donde instales el script:
// cie@iest.edu.mx  -> "alumnos"
// cte@iest.edu.mx  -> "maestros"
const TIPO_REPORTE = "alumnos";

const ETIQUETA_PROCESADO = `meet_api_enviado_${TIPO_REPORTE}`;
const ETIQUETA_ERROR = `meet_api_error_${TIPO_REPORTE}`;
const BUSQUEDA_BASE = 'from:meetings-noreply@google.com subject:"Registros de la reunión" newer_than:30d';

function procesarReportesMeetDirecto() {
  const token = PropertiesService.getScriptProperties().getProperty("MEET_API_TOKEN");

  if (!token) {
    throw new Error("Falta configurar la propiedad MEET_API_TOKEN en Apps Script.");
  }

  const labelProcesado = obtenerOCrearLabel_(ETIQUETA_PROCESADO);
  const labelError = obtenerOCrearLabel_(ETIQUETA_ERROR);
  const busqueda = `${BUSQUEDA_BASE} -label:${ETIQUETA_PROCESADO} -label:${ETIQUETA_ERROR}`;
  const threads = GmailApp.search(busqueda, 0, 20);

  threads.forEach(thread => {
    const messages = thread.getMessages();

    messages.forEach(message => {
      const subject = message.getSubject();
      const body = message.getBody();
      const spreadsheetId = extraerSpreadsheetId_(body);

      if (!spreadsheetId) {
        return;
      }

      try {
        const csv = convertirSheetACsvTexto_(spreadsheetId);
        const filename = `${TIPO_REPORTE}_${limpiarNombreArchivo_(subject)}.csv`;
        const payload = {
          tipo: TIPO_REPORTE,
          subject: subject,
          ingesta_id: message.getId(),
          filename: filename,
          csv: csv
        };

        const response = UrlFetchApp.fetch(ENDPOINT_API, {
          method: "post",
          contentType: "application/json; charset=utf-8",
          payload: JSON.stringify(payload),
          headers: {
            Authorization: `Bearer ${token}`
          },
          muteHttpExceptions: true
        });

        const status = response.getResponseCode();
        const text = response.getContentText();

        if (status < 200 || status >= 300) {
          throw new Error(`HTTP ${status}: ${text}`);
        }

        const result = JSON.parse(text);
        if (!result.ok) {
          throw new Error(text);
        }

        thread.addLabel(labelProcesado);
      } catch (error) {
        thread.addLabel(labelError);
        GmailApp.sendEmail(
          Session.getActiveUser().getEmail(),
          `[ERROR MEET API] ${subject}`,
          `No se pudo enviar la asistencia a la API.\n\nTipo: ${TIPO_REPORTE}\nAsunto: ${subject}\n\nError:\n${error}`
        );
      }
    });
  });
}

function extraerSpreadsheetId_(html) {
  const patrones = [
    /https:\/\/docs\.google\.com\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/,
    /https:\/\/drive\.google\.com\/open\?id=([a-zA-Z0-9-_]+)/,
    /https:\/\/drive\.google\.com\/file\/d\/([a-zA-Z0-9-_]+)/
  ];

  for (const patron of patrones) {
    const match = html.match(patron);
    if (match && match[1]) {
      return match[1];
    }
  }

  return "";
}

function convertirSheetACsvTexto_(spreadsheetId) {
  const spreadsheet = SpreadsheetApp.openById(spreadsheetId);
  const sheet = spreadsheet.getSheets()[0];
  const values = sheet.getDataRange().getDisplayValues();

  return values
    .map(row => row.map(escaparCsv_).join(","))
    .join("\n");
}

function escaparCsv_(value) {
  const texto = String(value ?? "");

  if (texto.includes(",") || texto.includes('"') || texto.includes("\n")) {
    return `"${texto.replace(/"/g, '""')}"`;
  }

  return texto;
}

function limpiarNombreArchivo_(texto) {
  return String(texto)
    .replace(/[\\/:*?"<>|]/g, "_")
    .replace(/\s+/g, "_")
    .substring(0, 120);
}

function obtenerOCrearLabel_(nombre) {
  return GmailApp.getUserLabelByName(nombre) || GmailApp.createLabel(nombre);
}

function crearActivadoresJornada() {
  eliminarActivadoresJornada();

  const horarios = [
    { h: 8, m: 30 },
    { h: 10, m: 0 },
    { h: 11, m: 30 },
    { h: 13, m: 0 },
    { h: 14, m: 30 },
    { h: 16, m: 0 },
    { h: 17, m: 30 },
    { h: 19, m: 0 },
    { h: 20, m: 30 }
  ];

  horarios.forEach(({ h, m }) => {
    ScriptApp.newTrigger("procesarReportesMeetDirecto")
      .timeBased()
      .atHour(h)
      .nearMinute(m)
      .everyDays(1)
      .inTimezone("America/Mexico_City")
      .create();
  });
}

function eliminarActivadoresJornada() {
  const triggers = ScriptApp.getProjectTriggers();

  triggers.forEach(trigger => {
    if (trigger.getHandlerFunction() === "procesarReportesMeetDirecto") {
      ScriptApp.deleteTrigger(trigger);
    }
  });
}
