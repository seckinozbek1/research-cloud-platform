FROM python:3.12-slim

WORKDIR /workspace

COPY src/run_pipeline.py /opt/pipeline/run_pipeline.py

CMD ["python", "/opt/pipeline/run_pipeline.py"]
