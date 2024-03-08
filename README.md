# Envmgr

`envmgr` is a tool for quick deployment to install and configure packages with ansible.

## Quick Start

### Dependencies

```bash
make dependency

# or

ansible-galaxy install -r requirements.yaml
```

### Config host

Host messages has been saved in `inventory/default.yaml`.

`master` group is for all and `worker` group is for kubernetes worker nodes.

```yaml
all:
  children:
    node:
      children:
        master:
          hosts: master1      # Change host here
        worker:
          hosts: worker[1:2]  # Change host here
```

### Start installation

Supported Setup Items:

- zsh
- python (default version: 3.10.4)
- node   (default version: 16.15.1)
- golang (default version: 1.20.4)
- ruby   (default version: 3.0.5)
- docker
- minikube
- kubeadm,kubelet (1.23.3-00)
- kubenetes tools:
  - kubectl (default version: 1.29)
  - helm

```bash
make total # All processes

make init # init

make skip-init # skip init
```

## Reference

【 [gantsign.oh-my-zsh](https://github.com/gantsign/ansible-role-oh-my-zsh) 】

【 [rvm.ruby](https://github.com/rvm/rvm1-ansible) 】
