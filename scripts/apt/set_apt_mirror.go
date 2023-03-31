// func main(){
// 	destr=$(lsb_release -is)
// 	version=$(lsb_release -rs)
// printf "=%.0s" {1..60}
// printf "\n=%.0s" {1..60}
// # sudo mv /etc/apt/sources.list /etc/apt/sources.list.bak
// # sudo cp -r ./source/${destr}_${version} /etc/apt/sources.list
// # sudo apt-get -y update

// }

package main

import (
	"fmt"
	"io/ioutil"
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
	yamlFile, err := ioutil.ReadFile("source.yaml")
	if err != nil {
		panic(err)
	}

	var distros map[string]Distro
	err = yaml.Unmarshal(yamlFile, &distros)
	if err != nil {
		panic(err)
	}
	current_distro, _ := Exec_cmd("lsb_release -is",true)
	current_version, _ := Exec_cmd("lsb_release -rs",false)
	fmt.Println(current_distro,current_version)
	fmt.Printf(
		"%s\n%s%s%s\n",
		strings.Repeat("=", 60),
		"Using "+current_distro+" "+current_version,
		strings.Repeat("=", 60))

	for key, distro := range distros {
		fmt.Println("Distro:", key)
		for _, os := range distro.OS {
			fmt.Println("  OS Version:", os.Version)
			fmt.Println("  OS Name:", os.Name)
			fmt.Println("  OS Source:")
			for _, source := range os.Source {
				fmt.Println("    -", source)
			}
		}
	}
}

func Exec_cmd(command string, isPrint bool) (string, error) {
	cmd := exec.Command("bash", "-c", command)
	output, err := cmd.Output()
	if err != nil {
		fmt.Println("Exec command failed:", err)
		return "", err
	}
	if isPrint {
		fmt.Println(string(output))
	}
		return string(output), nil
}
