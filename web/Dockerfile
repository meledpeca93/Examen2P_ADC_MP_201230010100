FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY web/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --requirement requirements.txt \
    && groupadd --system --gid 10001 web \
    && useradd --system --uid 10001 --gid web --create-home web

COPY --chown=10001:10001 web/ ./

USER 10001:10001
EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]