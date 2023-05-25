.PHONY: init

SHELL := /bin/bash
ENTRY_FILE := entry.yml
MASTER_FILE := master.yml

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

ruby:
	ansible-playbook $(ENTRY_FILE) -t ruby

master:
	ansible-playbook $(MASTER_FILE) 

master-minikube:
	ansible-playbook $(MASTER_FILE) -t minikube

lint:
	ansible-lint ./roles
