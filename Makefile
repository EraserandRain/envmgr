SHELL := /bin/bash
.PHONY: init

total:
	ansible-playbook entry.yml

init:
	ansible-playbook entry.yml -t init

zsh:
	ansible-playbook entry.yml -t zsh

node:
	ansible-playbook entry.yml -t node

lint:
	ansible-lint ./roles