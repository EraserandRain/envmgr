package main

import (
	"fmt"
	"os"
	"os/exec"
	"strings"

	yaml "gopkg.in/yaml.v3"
)

type Distro struct {
	Name string `yaml:"name"`
	OS   []struct {
		Version string   `yaml:"version"`
		Name    string   `yaml:"name"`
		Source  []string `yaml:"source"`
	} `yaml:"os"`
}

func main() {
	yamlFile, err := os.ReadFile("source.yaml")
	if err != nil {
		panic(err)
	}

	var distros map[string]Distro
	err = yaml.Unmarshal(yamlFile, &distros)
	if err != nil {
		panic(err)
	}

	current_distro, _ := Exec_cmd("lsb_release -is", false)
	current_version, _ := Exec_cmd("lsb_release -rs", false)
	fmt.Printf(
		"%s\n%s%s\n",
		strings.Repeat("=", 60),
		fmt.Sprintf("Current OS Version: %s %s\n", current_distro, current_version),
		strings.Repeat("=", 60))
	
	var current_source strings.Builder
	for key, distro := range distros {
		if key == current_distro {
			for _, os := range distro.OS {
				if os.Version == current_version {
					for _, source := range os.Source {
						current_source.WriteString(fmt.Sprintf("%s\n",source))
					}
				}
			}
		}
	}

	source_list := "/etc/apt/sources.list"
	source_list_bak := "/etc/apt/sources.list.bak"
	var cmd string = fmt.Sprintf("sudo mv %s %s",source_list,source_list_bak)
	Exec_cmd(cmd,true)
	cmd = fmt.Sprintf("echo -e %q | sudo tee -a %s",current_source.String(),source_list)
	Exec_cmd(cmd,true)
	cmd = "sudo apt-get -y update"
	Exec_cmd(cmd,true)
}

func Exec_cmd(command string, isPrint bool)   (string, error) {
	cmd := exec.Command("bash", "-c", command)
	output, err := cmd.Output()
	if err != nil {
		fmt.Println("Exec command failed:", err)
		return "", err
	}
	if isPrint {
		fmt.Println(string(output))
	}
	return strings.TrimRight(string(output), "\n"), nil
}
