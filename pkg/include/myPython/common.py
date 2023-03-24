# Import
import os
import shutil
import logging
import subprocess


# Define


def mkdir(path):
    isExists = os.path.exists(path)
    if not isExists:
        os.makedirs(path)
        return True
    else:
        return False
    pass


def rmdir(path):
    isExists = os.path.exists(path)
    if not isExists:
        return True
    else:
        shutil.rmtree(path)
        return False
    pass


def printlog(action, content, logpath):
    logger = logging.getLogger()
    logger.setLevel(logging.NOTSET)
    consoleHandler = logging.StreamHandler()
    consoleHandler.setLevel(logging.NOTSET)
    fileHandler = logging.FileHandler(
        logpath+action+'.log',
        mode='w',
        encoding='UTF-8'
    )
    fileHandler.setLevel(logging.NOTSET)
    formatter = logging.Formatter('%(asctime)s - %(message)s')
    consoleHandler.setFormatter(formatter)
    fileHandler.setFormatter(formatter)
    logger.addHandler(consoleHandler)
    logger.addHandler(fileHandler)
    logger.debug(content)
    pass


def cmd(command):
    print(f"command: {command}")
    os.system(command)
    pass

def grep(filename,keyword):
    proc =  subprocess.Popen("cat "+filename+" | grep "+keyword,stdout=subprocess.PIPE,shell=True)
    tmp = proc.stdout.readlines()
    for i in tmp:
        print(i.decode('utf-8'),end='')
    pass
