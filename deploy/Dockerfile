FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PORT=8080 SI_TRADER_MODE=hosted SI_TRADER_DATA_DIR=/data
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home trader && mkdir /data && chown trader:trader /data
COPY nifty100_weekly/ ./nifty100_weekly/
USER trader
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ['PORT']+'/healthz',timeout=4)"
CMD ["python", "-B", "-m", "nifty100_weekly.nifty100_adapter.web_app"]
