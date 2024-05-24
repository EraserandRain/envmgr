# Envmgr

`envmgr` is a tool for quick deployment to install and configure tools with ansible.

## Quick Start

### Dependencies

```bash
# Install poe plugin
poetry self add poethepoet 

# Install required dependencies
poe install-dep            
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
# install specified tools
poe install [tags] 

# install all
poe install all    

# install node
poe install node   
```

Supported Setup Items:

- zsh
- python (default version: 3.10.4)
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
poe ping
```

Create a new role

```bash
poe create [role]
```

## Reference

【 [gantsign.oh-my-zsh](https://github.com/gantsign/ansible-role-oh-my-zsh) 】

【 [rvm.ruby](https://github.com/rvm/rvm1-ansible) 】
