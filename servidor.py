# -*- coding: utf-8 -*-
"""Anonimizador local Soul IA (Presidio en espanol).

Corre 100% en local: nada sale del ordenador. Motor: Presidio (open source,
el mismo que se enseno en la formacion de Optimiza), configurado en espanol
(modelo spaCy es_core_news_md) + reconocedores propios de DNI/NIE y telefono ES.

Uso:  python servidor.py   ->  http://localhost:8741
"""
import json
import re
from http.server import HTTPServer, BaseHTTPRequestHandler

from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

PUERTO = 8741
import os as _os
MODO_WEB = _os.environ.get("ANONIMIZADOR_MODO", "local") == "web"

# ---------- motor en espanol ----------
provider = NlpEngineProvider(nlp_configuration={
    "nlp_engine_name": "spacy",
    "models": [{"lang_code": "es", "model_name": "es_core_news_md"}],
})

# DNI: 8 digitos + letra de control. NIE: X/Y/Z + 7 digitos + letra.
dni = PatternRecognizer(
    supported_entity="DNI_NIE", supported_language="es", name="dni_es",
    patterns=[
        Pattern("dni", r"\b\d{8}[ -]?[A-HJ-NP-TV-Z]\b", 0.6),
        Pattern("nie", r"\b[XYZ][ -]?\d{7}[ -]?[A-HJ-NP-TV-Z]\b", 0.6),
    ],
    context=["dni", "nie", "documento", "identidad", "nif"],
)
# Telefonos ES: moviles 6/7, fijos 8/9, con o sin +34, con espacios o puntos.
tel = PatternRecognizer(
    supported_entity="TELEFONO_ES", supported_language="es", name="tel_es",
    patterns=[Pattern("tel", r"(?<!\d)(?:\+34[ .-]?)?[6789]\d{2}[ .-]?\d{2,3}[ .-]?\d{2,3}[ .-]?\d{0,2}(?!\d)", 0.45)],
    context=["telefono", "movil", "llamar", "contacto", "tel"],
)
# Numero de la Seguridad Social (12 digitos con separadores tipicos)
nss = PatternRecognizer(
    supported_entity="NSS_ES", supported_language="es", name="nss_es",
    patterns=[Pattern("nss", r"\b\d{2}[ /-]?\d{8}[ /-]?\d{2}\b", 0.7)],
    context=["seguridad social", "nss", "afiliacion", "ss"],
)
# Email con CUALQUIER dominio (el detector estandar exige TLD real y se salta
# los .example de los materiales de formacion)
email = PatternRecognizer(
    supported_entity="EMAIL_ES", supported_language="es", name="email_es",
    patterns=[Pattern("email", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+\b", 0.9)],
    context=["email", "correo", "mail"],
)
# IBAN espanol, con o sin espacios/guiones
iban = PatternRecognizer(
    supported_entity="IBAN_ES", supported_language="es", name="iban_es",
    patterns=[Pattern("iban", r"\bES\d{2}(?:[ .-]?\d{4}){5}\b", 0.9)],
    context=["iban", "cuenta", "bancaria", "banco"],
)

analyzer = AnalyzerEngine(nlp_engine=provider.create_engine(), supported_languages=["es"])
analyzer.registry.add_recognizer(dni)
analyzer.registry.add_recognizer(tel)
analyzer.registry.add_recognizer(nss)
analyzer.registry.add_recognizer(email)
analyzer.registry.add_recognizer(iban)
anonymizer = AnonymizerEngine()

ETIQUETAS = {
    "PERSON": "NOMBRE", "DNI_NIE": "DNI", "ES_NIF": "DNI", "ES_NIE": "DNI",
    "TELEFONO_ES": "TELEFONO", "PHONE_NUMBER": "TELEFONO",
    "NSS_ES": "SEG_SOCIAL", "EMAIL_ADDRESS": "EMAIL", "EMAIL_ES": "EMAIL", "IBAN_ES": "IBAN",
    "LOCATION": "LUGAR", "ORGANIZATION": "EMPRESA",
    "IBAN_CODE": "IBAN", "CREDIT_CARD": "TARJETA",
    "URL": "URL", "DATE_TIME": "FECHA",
}
# DATE_TIME y URL suelen ser ruido en este uso: desactivadas por defecto
DESACTIVADAS = {"DATE_TIME", "URL"}
# falsos positivos tipicos del modelo en espanol (saludos como "lugar", etc.)
LISTA_BLANCA = {"buenos dias", "buenos días", "buenas tardes", "buenas noches",
                "buenas", "hola", "un saludo", "saludos", "gracias"}


def anonimizar(texto):
    candidatos = [r for r in analyzer.analyze(text=texto, language="es")
                  if r.entity_type not in DESACTIVADAS and r.score >= 0.4
                  and texto[r.start:r.end].strip().lower() not in LISTA_BLANCA]
    # dedupe de solapes: primero los reconocedores propios (especificos),
    # despues por confianza y longitud (el NER generico no pisa un DNI/NSS/IBAN)
    PROPIOS = {"DNI_NIE", "TELEFONO_ES", "NSS_ES", "EMAIL_ES", "IBAN_ES", "EMAIL_ADDRESS", "IBAN_CODE"}
    elegidos = []
    for r in sorted(candidatos, key=lambda x: (x.entity_type not in PROPIOS, -x.score, -(x.end - x.start))):
        if all(r.end <= k.start or r.start >= k.end for k in elegidos):
            elegidos.append(r)
    elegidos.sort(key=lambda x: x.start)

    # numerar cada tipo por VALOR: el mismo dato repite etiqueta (NOMBRE_1 siempre es Laura)
    contadores = {}
    detalles = []
    for r in elegidos:
        et = ETIQUETAS.get(r.entity_type, r.entity_type)
        original = texto[r.start:r.end]
        contadores.setdefault(et, {})
        if original not in contadores[et]:
            contadores[et][original] = len(contadores[et]) + 1
        detalles.append({
            "tipo": et, "texto": original,
            "sustituto": f"[{et}_{contadores[et][original]}]",
            "confianza": round(r.score, 2),
            "start": r.start, "end": r.end,
        })
    # reemplazo de atras hacia delante para no descolocar posiciones
    salida = texto
    for det in sorted(detalles, key=lambda x: -x["start"]):
        salida = salida[:det["start"]] + det["sustituto"] + salida[det["end"]:]
    for det in detalles:
        det.pop("start"); det.pop("end")
    return salida, detalles


PAGINA = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Anonimizador local · Soul IA</title>
<style>
:root { --bg:#0D0D0D; --card:#161616; --naranja:#E2601F; --cian:#35C5DD; --verde:#8FD694; --gris:#B8B8B8; }
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:#EDEDED; font-family:"Segoe UI",system-ui,sans-serif; padding:34px 5vw 60px; }
header { display:flex; align-items:center; gap:14px; margin-bottom:6px; }
header b { font-size:1.35rem; } header b span { color:var(--cian); }
.escudo { width:46px; height:46px; border-radius:12px; background:rgba(143,214,148,.12); border:1px solid var(--verde); display:flex; align-items:center; justify-content:center; flex:none; }
.escudo svg { width:26px; height:26px; stroke:var(--verde); fill:none; stroke-width:1.8; stroke-linecap:round; stroke-linejoin:round; }
.titulo-app { font-size:1.05rem; letter-spacing:2.5px; text-transform:uppercase; color:#fff; font-weight:700; }
.badge-local { border:1px solid var(--verde); background:rgba(143,214,148,.1); color:var(--verde); border-radius:20px; padding:5px 16px; font-size:.8rem; letter-spacing:1px; font-weight:700; }
.sub { color:var(--gris); margin:6px 0 18px; max-width:74ch; line-height:1.5; }
.sub b { color:#fff; }
.sellos { display:flex; gap:10px; flex-wrap:wrap; margin-bottom:26px; }
.sello { display:flex; align-items:center; gap:8px; background:var(--card); border:1px solid #263A2C; border-radius:10px; padding:9px 14px; font-size:.86rem; color:var(--gris); }
.sello svg { width:17px; height:17px; stroke:var(--verde); fill:none; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; flex:none; }
.sello b { color:var(--verde); font-weight:700; }
.cols { display:grid; grid-template-columns:1fr 1fr; gap:18px; }
textarea, .salida { width:100%; min-height:320px; background:#0A0A0A; border:1px solid #2E2E2E; border-radius:10px; padding:16px 18px; color:#E8E8E8; font-size:1rem; line-height:1.55; font-family:inherit; }
textarea:focus { outline:none; border-color:var(--verde); }
.salida { white-space:pre-wrap; overflow-y:auto; }
.salida mark { background:#12312A; color:var(--verde); border-radius:4px; padding:0 4px; font-weight:600; }
h3 { font-size:.85rem; letter-spacing:2px; text-transform:uppercase; color:var(--gris); margin:0 0 10px; }
.acciones { margin:16px 0; display:flex; gap:10px; flex-wrap:wrap; }
.btn { border:none; border-radius:8px; padding:12px 22px; font-size:1rem; cursor:pointer; font-weight:700; }
.btn-p { background:var(--naranja); color:#fff; }
.btn-s { background:var(--card); color:var(--cian); border:1px solid var(--cian); }
.btn-s.ok { color:var(--verde); border-color:var(--verde); }
#hallazgos { margin-top:22px; display:flex; gap:8px; flex-wrap:wrap; }
#hallazgos span { background:var(--card); border:1px solid #2E2E2E; border-radius:20px; padding:6px 14px; font-size:.88rem; color:var(--gris); }
#hallazgos span b { color:var(--verde); }
footer { margin-top:34px; color:#6B6B6B; font-size:.82rem; }
@media (max-width:800px){ .cols{grid-template-columns:1fr;} }
</style></head><body>
<header>
  <div class="escudo"><svg viewBox="0 0 24 24"><path d="M12 3 5 6v6c0 4.5 3 7.5 7 9 4-1.5 7-4.5 7-9V6z"/><path d="m9 12 2 2 4-4.5"/></svg></div>
  <div><div class="titulo-app">Anonimizador local</div><b>SOUL <span>IA</span></b></div>
  <span class="badge-local">__BADGE__</span>
</header>
<p class="sub">Motor <b>Microsoft Presidio</b> (open source) configurado en <b>español</b>: nombres, DNI/NIE, teléfonos, emails, IBAN y Seguridad Social. Pega el texto, anonimiza y trabaja con la versión limpia.</p>
<div class="sellos">
  <span class="sello"><svg viewBox="0 0 24 24"><rect x="4" y="10" width="16" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg>__SELLO1__</span>
  <span class="sello"><svg viewBox="0 0 24 24"><path d="m8 8-4 4 4 4M16 8l4 4-4 4"/></svg><b>Código abierto</b> y auditable (licencia MIT)</span>
  <span class="sello"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 3"/></svg><b>Al instante:</b> corre en este mismo equipo</span>
  <span class="sello"><svg viewBox="0 0 24 24"><path d="M12 3 5 6v6c0 4.5 3 7.5 7 9 4-1.5 7-4.5 7-9V6z"/></svg><b>RGPD por diseño:</b> el dato nunca sale de tu control</span>
</div>
<div class="cols">
  <div><h3>Texto original</h3><textarea id="entrada" placeholder="Pega aquí el texto con datos personales..."></textarea></div>
  <div><h3>Texto anonimizado</h3><div class="salida" id="salida"></div></div>
</div>
<div class="acciones">
  <button class="btn btn-p" onclick="procesar()">Anonimizar</button>
  <button class="btn btn-s" id="btn-copiar" onclick="copiarSalida(this)">Copiar anonimizado</button>
  <button class="btn btn-s" onclick="ejemplo()">Cargar ejemplo</button>
</div>
<div id="hallazgos"></div>
<footer>__FOOTER__ Proyecto open source (licencia MIT), el mismo motor que usan entornos empresariales para proteger datos antes de que lleguen a cualquier IA. Configuración en español por Soul IA · Masterclass Informa Consultores.</footer>
<script>
let textoPlano = '';
async function procesar(){
  const t = document.getElementById('entrada').value;
  if(!t.trim()) return;
  document.getElementById('salida').textContent = 'Analizando...';
  let d;
  try {
    const r = await fetch('/anonimizar', {method:'POST', body: JSON.stringify({texto:t})});
    d = await r.json();
    if (d.error) throw new Error(d.error);
  } catch(e) {
    document.getElementById('salida').textContent = 'Hubo un error al analizar. Prueba otra vez (o reinicia el servidor).';
    return;
  }
  textoPlano = d.salida;
  let html = d.salida.replace(/&/g,'&amp;').replace(/</g,'&lt;');
  html = html.replace(/\\[([A-Z_]+_\\d+)\\]/g, '<mark>[$1]</mark>');
  document.getElementById('salida').innerHTML = html;
  const porTipo = {};
  d.detalles.forEach(x => porTipo[x.tipo] = (porTipo[x.tipo]||0)+1);
  document.getElementById('hallazgos').innerHTML =
    d.detalles.length
    ? Object.entries(porTipo).map(([k,v])=>`<span><b>${v}</b> ${k}</span>`).join('')
    : '<span>Sin datos personales detectados</span>';
}
function copiarSalida(btn){
  if(!textoPlano) return;
  const done = ()=>{ btn.textContent='Copiado ✓'; btn.classList.add('ok'); setTimeout(()=>{btn.textContent='Copiar anonimizado'; btn.classList.remove('ok');},1800); };
  if(navigator.clipboard && navigator.clipboard.writeText){ navigator.clipboard.writeText(textoPlano).then(done); }
  else { const ta=document.createElement('textarea'); ta.value=textoPlano; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); document.body.removeChild(ta); done(); }
}
function ejemplo(){
  document.getElementById('entrada').value = 'Buenos dias, soy Laura Gutierrez Manzano, administrativa de Distribuciones Guadalmar. Mi DNI es 51884203X y mi movil el 677 412 985. Os escribo desde laura.gutierrez89@gmail.com por el curso de ofimatica. Mi companero Antonio Reyes (areyes@talleresaxarquia.example, tel 615 468 557) tambien quiere apuntarse. Vivo en Calle Almogia 17, Malaga.';
  procesar();
}
</script></body></html>"""


if MODO_WEB:
    PAGINA = (PAGINA
        .replace("__BADGE__", "🌐 DEMO ONLINE · para probar la herramienta")
        .replace("__SELLO1__", "<b>Esto es la demo:</b> para datos reales, la versión local (nada sale de tu equipo)")
        .replace("__FOOTER__", "🌐 Demo online del anonimizador de Soul IA (motor Microsoft Presidio, open source, configurado en español). Para trabajar con datos reales se instala EN VUESTRO equipo o servidor: ahí ninguna petición sale de vuestra casa."))
else:
    PAGINA = (PAGINA
        .replace("__BADGE__", "🔒 100% LOCAL · nada sale de este ordenador")
        .replace("__SELLO1__", "<b>Sin nube:</b> el texto no viaja a ningún servidor")
        .replace("__FOOTER__", "🔒 Microsoft Presidio corriendo en este equipo (localhost): ninguna petición sale de tu ordenador."))


class Manejador(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(PAGINA.encode("utf-8"))

    def do_POST(self):
        if self.path != "/anonimizar":
            self.send_response(404); self.end_headers(); return
        try:
            largo = int(self.headers.get("Content-Length", 0) or 0)
            datos = json.loads(self.rfile.read(largo).decode("utf-8"))
            salida, detalles = anonimizar(datos.get("texto", "")[:50000])
            cuerpo = json.dumps({"salida": salida, "detalles": detalles}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
        except Exception as e:
            cuerpo = json.dumps({"error": str(e)[:200]}, ensure_ascii=False).encode("utf-8")
            self.send_response(500)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(cuerpo)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    import os
    # en local se queda en 127.0.0.1 (nada sale del equipo); en Docker, 0.0.0.0
    host = os.environ.get("ANONIMIZADOR_HOST", "127.0.0.1")
    print(f"Anonimizador local Soul IA -> http://localhost:{PUERTO}  (Ctrl+C para parar)")
    HTTPServer((host, PUERTO), Manejador).serve_forever()
