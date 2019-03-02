FROM python:3.6-alpine3.8

ADD . /usr/src/app
WORKDIR /usr/src/app

RUN ["python", "setup.py", "develop"]

CMD ["ecs"]
