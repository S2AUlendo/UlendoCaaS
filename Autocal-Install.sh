#!/bin/sh
# NOTES
# script should be made executable via chmod +x
# source the script when executing so that the directories are created by the main shell and not subshell, 
# i.e. ". ./Autocal-Install.sh" 

# apt requires root, as does systemctl
sudo -n true
test $? -eq 0 || exit -1 "script must be run as root to install dependencies"

# list them in one place for ease of updating
DEPENDENCIES="python3 python3-pip python3-dev python3-setuptools python3-venv git libyaml-dev build-essential libffi-dev libssl-dev libopenblas-dev liblapack-dev pigpio gcc g++ gfortran"

# update apt and the OS
sudo apt update
sudo apt upgrade -y

# install all dependencies and say yes to space used prompt
sudo apt install -y $DEPENDENCIES

# install GPIO service and enable it for the accelerometer
sudo systemctl enable pigpiod
sudo pigpiod

# the python virtual environment, octoprint, and the plugin will be installed here
cd ~
mkdir -p OctoPrint && cd OctoPrint

# create the virtual environment
python3 -m venv venv
source venv/bin/activate
# update pip and wheel
pip install --upgrade pip wheel
# install IO and Octoprint
pip install control
pip install pigpio
pip install octoprint

# get the plugin
git clone https://github.com/S2AUlendo/UlendoCaaS.git OctoPrint-Autocal

# install the plugin
cd OctoPrint-Autocal
../venv/bin/octoprint dev plugin:install

# start the server
cd ~/OctoPrint
venv/bin/octoprint serve