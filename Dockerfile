FROM python:3.13-alpine

ADD . /usr/src/app
WORKDIR /usr/src/app

RUN ["python", "-m", "pip", "install", "-r", "requirements.txt"]
RUN ["python", "-m", "pip", "install", "."]

CMD ["ecs"]
