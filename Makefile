IMAGE_NAME     ?= sre/ecs-deploy
BUILD_TAG      ?= build-local
REGISTRY       ?= 404977151305.dkr.ecr.eu-central-1.amazonaws.com
IMAGE_URI      ?= ${REGISTRY}/${IMAGE_NAME}:${BUILD_TAG}

TEST_FILE      ?= ...

.PHONY: build

build:
	docker build --pull -t ${IMAGE_URI} .
