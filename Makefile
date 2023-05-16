SHELL := /bin/bash
.PHONY: init

init:
	ansible-playbook entry.yml --skip-tags init

lint:
	ansible-lint ./roles