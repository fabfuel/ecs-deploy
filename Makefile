IMAGE_NAME     ?= sre/ecs-deploy
BUILD_TAG      ?= build-local
REGISTRY       ?= 404977151305.dkr.ecr.eu-central-1.amazonaws.com
IMAGE_URI      ?= ${REGISTRY}/${IMAGE_NAME}:${BUILD_TAG}

TEST_FILE      ?= ...

.PHONY: build

build:
	docker build --pull -t ${IMAGE_URI} .

test: build
	docker run -t --rm $(IMAGE_URI) pytest -p no:cacheprovider -x -vv /usr/src/app

dev: build
	docker run -it --rm -v $(PWD):/usr/src/app $(IMAGE_URI) bash