FROM python:3.11-slim

WORKDIR /app
COPY requisitos.txt .
RUN pip install --no-cache-dir -r requisitos.txt \
    && python -m spacy download es_core_news_md

COPY servidor.py .

# dentro del contenedor hay que escuchar en 0.0.0.0 (Traefik hace de puerta)
ENV ANONIMIZADOR_HOST=0.0.0.0
EXPOSE 8741
CMD ["python", "-X", "utf8", "servidor.py"]
