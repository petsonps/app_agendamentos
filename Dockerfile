FROM python:3.8-slim

ADD . /app
WORKDIR /app

CMD [ "python", "app.py" ]