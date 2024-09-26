#!/bin/bash

# Update and install system packages
sudo apt update
sudo apt install -y python3 python3-pip python3-dev python3-setuptools python3-venv git libyaml-dev build-essential libffi-dev libssl-dev
sudo apt install -y libopenblas-dev
sudo apt install -y pigpio

# Enable and start pigpiod
sudo systemctl enable pigpiod
sudo pigpiod

# Install pip packages
pip install --upgrade pip wheel
pip install pigpio

# Set up OctoPrint
cd ~
mkdir OctoPrint
cd OctoPrint
python3 -m venv venv
source venv/bin/activate

pip install octoprint

echo "Installation complete. You may need to reboot your system."
echo "To reboot, run: sudo shutdown -r now"
