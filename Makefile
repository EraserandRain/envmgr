SHELL := /bin/bash
LIST := a b c

build: build_all

build_%:
	@if [[ "$*" == "all" ]]; then \
		echo $(LIST); \
	elif [[ "$(LIST)" == *"$*"* ]]; then \
		echo $*; \
	else \
		echo "Error: $* not found in the list ($(LIST)))"; \
	fi
	