#!/bin/bash
export LC_ALL=C
cd /etc/yum.repos.d/
mkdir -p bak
mv * bak/
curl -o /etc/yum.repos.d/CentOS-Base.repo http://file.kangle.odata.cc/repo/Centos-6.repo
curl -o /etc/yum.repos.d/epel.repo http://file.kangle.odata.cc/repo/epel-6.repo
yum clean all
yum makecache
exit 0
