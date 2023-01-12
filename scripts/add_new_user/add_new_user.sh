#!/usr/bin/env bash
NEW_USER='eraserrain'
NEW_GROUPS='eraserrain'
PASS_WORD='Abcd1234'

id -u ${NEW_USER} >/dev/null 2>&1
if [[ $? -ne 0 ]]; then
    groupadd ${NEW_GROUPS}
    useradd ${NEW_USER} -s /bin/bash -g ${NEW_GROUPS} -G sudo -d "/home/${NEW_USER}" -m
    echo ${NEW_USER}:${PASS_WORD} | chpasswd
    bash -c "echo '${NEW_USER} ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/${NEW_USER}"