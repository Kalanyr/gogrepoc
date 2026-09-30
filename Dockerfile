ARG PYTHON_VERSION=3.10

FROM python:${PYTHON_VERSION}

RUN mkdir /app
COPY . /app
WORKDIR /app
RUN pip install --no-cache-dir -r requirements.txt

VOLUME /storage/
WORKDIR /storage/
ENTRYPOINT ["python", "/app/gogrepoc.py"]
