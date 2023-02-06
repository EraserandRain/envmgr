#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc, char *argv[])
{
    char *home = getenv("HOME");
    // printf("%s\n", strcat(home,"/c"));
    printf("%s\n", home);
    if (argc == 2)
    {
        switch (argv[1])
        {
        case '-c':
            strcat(home, "/learn/c");
            break;
        case '-cpp':
            strcat(home, "/learn/cpp");
            break;
        case '-python':
            strcat(home, "/learn/python");
            break;
        case '-golang':
            strcat(home, "/learn/golang");
            break;
        }
        chdir(home);
    }
    else if (argc > 2)
    {
        printf("Too many arguments supplied.\n");
    }
    else
    {
        printf("One argument expected.\n");
    }
}
