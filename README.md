# Envmgr
Quick Deployment to install and configure packages with ansible.
## Quick Start
### Dependencies

```bash
ansible-galaxy collection install \
    community.general

ansible-galaxy install \
    gantsign.oh-my-zsh \
    stephdewit.nvm \
    rvm.ruby
```
### Config host
Host messages has been save in `inventory/default.yaml`.

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
- docker
- ruby   (default version: 3.0.5)
- minikube
- kubeadm,kubectl,kubelet (1.23.3-00) 
```bash
make total # All processes

make init # init

make skip-init # skip init
```

## Reference
【 [gantsign.oh-my-zsh](https://github.com/gantsign/ansible-role-oh-my-zsh) 】

【 [rvm.ruby](https://github.com/rvm/rvm1-ansible) 】
