# Anonimizador Soul IA

Anonimizador de datos personales en ESPANOL, construido sobre Microsoft Presidio
(open source). Detecta y sustituye con etiquetas consistentes: nombres, DNI/NIE,
telefonos, emails (cualquier dominio), IBAN, numeros de la Seguridad Social,
lugares y organizaciones.

Corre 100% en local: `python -X utf8 servidor.py` -> http://localhost:8741

Requisitos: `pip install -r requisitos.txt && python -m spacy download es_core_news_md`

Docker: `docker compose up -d`

Licencia MIT. Un proyecto de [Soul IA](https://soulia.io).
