FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DJANGO_SETTINGS_MODULE=config.render
WORKDIR /app
COPY requirements.txt requirements-production.txt ./
RUN python -m pip install --no-cache-dir -r requirements-production.txt \
    && groupadd --system taskflow \
    && useradd --system --gid taskflow taskflow \
    && mkdir /app/staticfiles \
    && chown taskflow:taskflow /app/staticfiles
COPY config/ config/
COPY apps/ apps/
COPY manage.py ./
COPY deploy/start.sh deploy/start.sh
RUN sed -i 's/\r$//' deploy/start.sh
USER taskflow
EXPOSE 10000
CMD ["/bin/sh", "deploy/start.sh"]
