FROM python:3.14

COPY requirements.txt /

RUN pip install -r /requirements.txt

WORKDIR /app

COPY remote_nfc_spool_reader.py .

CMD /app/remote_nfc_spool_reader.py
