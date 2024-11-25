FROM python:3.10-alpine

COPY requirements-test.txt .
RUN pip install -r requirements-test.txt

ADD . /usr/src/app
WORKDIR /usr/src/app

RUN ["python", "setup.py", "install"]

CMD ["ecs"]
