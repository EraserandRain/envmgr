#!/bin/bash
export LC_ALL=C
cd /etc/yum.repos.d/
mkdir -p bak
mv * bak/
curl -o /etc/yum.repos.d/CentOS-Base.repo https://mirrors.aliyun.com/repo/Centos-7.repo
curl -o /etc/yum.repos.d/epel.repo http://mirrors.aliyun.com/repo/epel-7.repo
yum clean all
yum makecache
exit 0
