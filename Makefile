SHELL := /bin/bash
.PHONY: init

init:
	# ansible-playbook entry.yml
	ansible-playbook entry.yml --skip-tags init

zsh:
	ansible-playbook entry.yml -t zsh

lint:
	ansible-lint ./roles