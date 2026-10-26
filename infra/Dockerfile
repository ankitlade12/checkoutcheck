FROM python:3.14.0-slim
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir torch==2.14.1 torchvision==0.29.1 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.lock
COPY checkoutcheck ./checkoutcheck
COPY apps/web ./apps/web
COPY docs ./docs
RUN useradd --uid 10001 --create-home checkoutcheck && mkdir /data && chown checkoutcheck /data
USER checkoutcheck
ENV CHECKOUTCHECK_DATA=/data
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/v1/health', timeout=3)"
CMD ["python", "-m", "uvicorn", "checkoutcheck.server:app", "--host", "0.0.0.0", "--port", "8765"]
