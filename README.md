# Envmgr

`envmgr` is a tool for quick deployment to install and configure tools with ansible.

## Quick Start

### Dependencies

Envmgr requires Python 3.8 or later and the rye package.

Please install `rye` first 【[rye installation](https://rye.astral.sh/guide/installation/)】.

```bash
# Install rye
curl -sSf https://rye.astral.sh/get | RYE_INSTALL_OPTION="--yes" bash

# Setup envmgr
rye run setup            
```

### Host Settings

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

### Setup Tools

Setup specified tools

```bash
# Install specified tools
rye run install [tag1 tag2 ...] 

# Install all roles
rye run install all    

# Install zsh
rye run install zsh   

# List available tags
rye run install -l
```

Supported Setup Items:

- zsh
- node   (default version: 16.15.1)
- golang (default version: 1.20.4)
- ruby   (default version: 3.0.5)
- docker
- minikube (latest)
- kubeadm,kubelet (1.23.3-00)
- kubenetes tools:
  - kubectl (default version: 1.29)
  - helm
- cloud
  - awscli

Test connection

```bash
rye run ping
```

Create a new role

```bash
rye run create [role]
```

## Reference

【[rye](https://rye.astral.sh/guide)】

【 [gantsign.oh-my-zsh](https://github.com/gantsign/ansible-role-oh-my-zsh) 】

【 [rvm.ruby](https://github.com/rvm/rvm1-ansible) 】
