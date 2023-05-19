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

lint:
	ansible-lint ./roles