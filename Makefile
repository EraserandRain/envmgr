.PHONY: init

SHELL := /bin/bash
ENTRY_FILE := entry.yml

total:
	ansible-playbook $(ENTRY_FILE)

init:
	ansible-playbook $(ENTRY_FILE) -t init

zsh:
	ansible-playbook $(ENTRY_FILE) -t zsh

python:
	ansible-playbook $(ENTRY_FILE) -t python

node:
	ansible-playbook $(ENTRY_FILE) -t node

golang:
	ansible-playbook $(ENTRY_FILE) -t golang

docker:
	ansible-playbook $(ENTRY_FILE) -t docker

lint:
	ansible-lint ./roles