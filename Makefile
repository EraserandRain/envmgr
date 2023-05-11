SHELL := /bin/bash
.PHONY: init

init:
	ansible-playbook entry.yml 
	# ansible-playbook entry.yml --skip-tags sshkey
	# ansible-playbook entry.yml --skip-tags sshkey -vvv
