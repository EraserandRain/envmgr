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
| `set_apt_mirror`      | Set Tsinghua Mirror for `apt`                               |
| `disable_needrestart` | Disable "needrestart" feature in Ubuntu 22.04               |
| `set_git_config`      | Git configuration                                           |
| `wsl2_config`         | WSL2 configuration,                                         |

| **Options in `install_env`** | **Description**                                                            |
| ---------------------------- | -------------------------------------------------------------------------- |
| `node`                       | Install `node`,`nvm`,`nrm`                                                 |
| `python`                     | Install `python3`,`pip3`                                                   |
| `cpp`                        | Install `gcc`,`automake`,`autoconf`,`libtool`,`make`,`build-essential gdb` |
| `ubuntu_docker`              | Install `docker`,`docker-compose`                                          |
| `zsh`                        | Install `zsh`,`oh-my-zsh`                                                  |

| **Options in `load_env`** | **Description**       |
| ------------------------- | --------------------- |
| `compose`                 | Load `docker-compose` |
| `zsh`                     | Load `zsh`            |
| `nvm`                     | Load `nvm`            |
| `vagrant`                 | Load `vagrant`        |
| `alias`                   | Load `alias`          |

| **Options in `wsl2_config`** | **Description**              |
| ---------------------------- | ---------------------------- |
| `fix_interop`                | Fix interop bug in WSL       |
| `startup_docker`             | Config docker startup in WSL |