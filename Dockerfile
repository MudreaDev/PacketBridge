FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY packetbridge ./packetbridge
USER 65534:65534
EXPOSE 8765
ENTRYPOINT ["python", "-m", "packetbridge.relay"]
CMD ["--bind", "0.0.0.0"]
