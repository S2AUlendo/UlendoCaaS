#!/bin/bash

# Check if script is run as root
if [ "$EUID" -ne 0 ]
  then echo "Please run as root"
  exit
fi

# Update and install system packages
apt update
apt install -y systemd python3 python3-pip python3-dev python3-setuptools python3-venv python3-full git libyaml-dev build-essential libffi-dev libssl-dev
apt install -y libopenblas-dev
apt install -y pigpio

# Enable and start pigpiod
systemctl enable pigpiod
pigpiod

# Prompt for username
read -p "Enter your username: " USERNAME

# Set up OctoPrint
su - $USERNAME << EOF
cd ~
mkdir OctoPrint
cd OctoPrint
python3 -m venv venv
source venv/bin/activate
# Install pip packages within the virtual environment
pip install --upgrade pip wheel
pip install pigpio
pip install octoprint
deactivate
EOF

echo "Installation complete. Now setting up OctoPrint as a background service."

# Create the service file
cat > /etc/systemd/system/octoprint.service << EOL
[Unit]
Description=OctoPrint
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USERNAME
ExecStart=/home/$USERNAME/OctoPrint/venv/bin/octoprint serve
WorkingDirectory=/home/$USERNAME/.octoprint
Restart=always
RestartSec=60

[Install]
WantedBy=multi-user.target
EOL

# Reload systemd
systemctl daemon-reload

# Enable the service
systemctl enable octoprint.service

# Start the service
systemctl start octoprint.service

# Check the status
systemctl status octoprint.service

echo "OctoPrint service has been set up and started."
echo "You can access it at http://localhost:5000 or http://<your_device_ip>:5000"
echo "To check the status, use: sudo systemctl status octoprint.service"
echo "To view logs, use: sudo journalctl -u octoprint.service"
