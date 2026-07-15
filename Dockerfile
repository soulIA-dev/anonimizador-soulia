FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m spacy download es_core_news_md

COPY servidor.py .

# dentro del contenedor hay que escuchar en 0.0.0.0 (Traefik hace de puerta)
ENV ANONIMIZADOR_HOST=0.0.0.0
EXPOSE 8741
CMD ["python", "-X", "utf8", "servidor.py"]
