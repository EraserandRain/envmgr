## Usage
```bash
# Export script
source ~/install/include/common.sh

# Install Packages
install_env \
--node \
...

# Load Env
load_env \
--nvm \
...

# WSL2 Config
wsl2_config \
--fix_interop \
--startup_docker \
...
```

## Function Description

| **Function**          | **Description**                                             |
| --------------------- | ----------------------------------------------------------- |
| `install_env`         | Install packages                                            |
| `load_env`            | Load env                                                    |
| `if_jammy_os`         | Judge if Ubuntu 22.04 OS or not , if true , execute command |
| `disable_needrestart` | Disable "needrestart" feature in Ubuntu 22.04               |
| `wsl2_config`         | WSL2 configuration                                          |

| **Options in `install_env`** | **Description**                                                            |
| ---------------------------- | -------------------------------------------------------------------------- |
| `node`                       | Install `node nvm nrm`                                                 |
| `python`                     | Install `python3 pip3`                                                   |
| `cpp`                        | Install `gcc automake autoconf libtool make build-essential gdb` |
| `docker`                     | Install `docker docker-compose`                                          |
| `zsh`                        | Install `zsh oh-my-zsh`                                                  |
| `golang`                     | Install `go1.18 gvm`                                                           |

| **Options in `load_env`** | **Description**               |
| ------------------------- | ----------------------------- |
| `alias`                   | Load `alias`                  |
| `apt`                     | Set Tsinghua Mirror for `apt` |
| `compose`                 | Load `docker-compose`         |
| `git`                     | Git config                    |
| `golang`                  | Load `golang`                 |
| `nvm`                     | Load `nvm`                    |
| `pyenv`                   | Load `pyenv`                  |
| `ssh`                     | SSH config                    |
| `vagrant`                 | Load `vagrant`                |
| `vim`                     | Vim config                    |
| `zsh`                     | Load `zsh`                    |

| **Options in `wsl2_config`** | **Description**              |
| ---------------------------- | ---------------------------- |
| `fix_interop`                | Fix interop bug in WSL       |
| `startup_docker`             | Config docker startup in WSL |