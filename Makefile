# Recontool — convenience targets
# Usage:
#   make build          # build the Docker image (installs ALL tools)
#   make scan T=groww.in  # run a full scan
#   make demo           # zero-network demo
#   make push           # push to Docker Hub (set DOCKER_REPO)

DOCKER_REPO ?= recontool
IMAGE := $(DOCKER_REPO):latest
TARGET ?= groww.in

.PHONY: build scan demo push shell test

build:
	docker compose build

scan:
	docker compose run --rm recontool scan $(TARGET) --mode live --authorize-active --timeout 300

demo:
	docker compose run --rm recontool demo

shell:
	docker compose run --rm --entrypoint bash recontool

test:
	docker compose run --rm --entrypoint pytest recontool tests/ -q

push:
	docker tag recontool:latest $(DOCKER_REPO):latest
	docker push $(DOCKER_REPO):latest

clean:
	rm -rf output/ artifacts/ recontool.db
