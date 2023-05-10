SHELL := /bin/bash
.PHONY: init

init:
	ansible-playbook entry.yml --skip-tags sshkey
