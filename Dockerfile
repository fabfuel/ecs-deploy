FROM --platform=linux/amd64 python:3.10-alpine3.15

ADD . /usr/src/app
WORKDIR /usr/src/app

RUN ["python", "setup.py", "install"]

RUN apk --no-cache add bash

CMD ["ecs"]
