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

# get current user
USER="$(whoami)"
echo "current user = $USER"

INSTALL="/home/$USER/OctoPrint"
PLUGIN="/home/$USER/OctoPrint/OctoPrint-Autocal"

# update apt and the OS
sudo apt update
sudo apt upgrade -y

# install all dependencies and say yes to space used prompt
sudo apt install -y $DEPENDENCIES

# install GPIO service and enable it for the accelerometer
sudo systemctl enable pigpiod
sudo pigpiod

# if OctoPrint has been installed, update it 
if [ -d "/home/$USER/OctoPrint" ]
then
  # if the plugin has been installed before, pull the latest version
  if [ -d "/home/$USER/OctoPrint/OctoPrint-Autocal" ]
  then
    cd $PLUGIN
    git pull origin main
    git fetch --tags
    latestTag=$(git describe --tags "$(git rev-list --tags --max-count=1)")
    git checkout $latestTag    
  fi
fi

# if the OctoPrint dir doesn't exist, perform a fresh install
if [ ! -d "/home/$USER/OctoPrint" ] 
then
  # the python virtual environment, octoprint, and the plugin will be installed here
  cd ~
  mkdir -p OctoPrint && cd OctoPrint

  # create the virtual environment
  python3 -m venv venv
  source venv/bin/activate
  # update pip and wheel
  pip install --upgrade pip wheel
  # install IO and Octoprint
  pip install pigpio
  pip install octoprint

  # get the plugin
  git clone https://github.com/S2AUlendo/UlendoCaaS.git OctoPrint-Autocal
  cd OctoPrint-Autocal
  git fetch --tags
  latestTag=$(git describe --tags "$(git rev-list --tags --max-count=1)")
  git checkout $latestTag 

  # install the plugin
  cd OctoPrint-Autocal
  ../venv/bin/octoprint dev plugin:install

  #leave the python virtual environment
  deactivate

fi

# create the octoprint system service
SERVICE="[Unit]
Description=Octoprint Service
After=network-online.target
Wants=network-online.target

[Service]
Environment=\"LC_ALL=C.UTF-8\"
Environment=\"LANG=C.UTF-8\"
Type=exec
User=$USER
ExecStart=/home/$USER/OctoPrint/venv/bin/octoprint  

[Install]
WantedBy=multi-user.target"

echo "$SERVICE" | sudo tee /etc/systemd/system/octoprint.service >/dev/null

# enable and start the octoprint system service
sudo systemctl daemon-reload
sudo systemctl enable octoprint.service
sudo service octoprint start

#return home
cd ~
echo "installation complete"
