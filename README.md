# Calibration as a Service

Ulendo's Calibration as a Service

# Instructions to Autocalibrate in Octoprint

## Setup (RPi)

	sudo apt update
	sudo apt install python3 python3-pip python3-dev python3-setuptools python3-venv git libyaml-dev build-essential libffi-dev libssl-dev
	sudo apt install libopenblas-dev (this is for numpy, we'll remove this dependency in the near future)
	sudo apt install pigpio

 	sudo systemctl enable pigpiod
  
	sudo pigpiod
		-or-
	sudo shutdown -r now
	
	pip install --upgrade pip wheel
	pip install pigpio
	
	cd ~
	mkdir OctoPrint
	cd OctoPrint
	python3 -m venv venv
	source venv/bin/activate
	
	pip install octoprint
	
	
	git clone https://github.com/S2AUlendo/UlendoCaaS.git OctoPrint-Autocal
	cd OctoPrint-Autocal
	../venv/bin/octoprint dev plugin:install
	
	
	Additional installation to use scipy package locally:
		sudo apt-get install gcc g++ gfortran python3-dev libopenblas-dev liblapack-dev
	Additional installation to use control package locally:
	 	sudo apt-get install libopenjp2-7-dev
		pip install control


## Setup (Windows)

	cd c:\
	mkdir OctoPrint
	cd OctoPrint
	py -m venv venv
	venv\Scripts\activate.bat
	
	pip install --upgrade pip wheel
	pip install octoprint
	
	git clone https://github.com/S2AUlendo/UlendoCaaS.git OctoPrint-Autocal
	cd OctoPrint-Autocal
	octoprint dev plugin:install


## Usage (RPi):

	Run octoprint as usual:
		source venv/bin/activate
		venv/bin/octoprint serve
		
	Note: You may use PuTTY Secury Copy (pscp) to transfer data between machines, e.g.:
		pscp pi@octopi.local:/home/pi/rasppi-tools/accout.csv c:\Users\ulendoalex\Documents


## Usage (Windows):

	Run octoprint as usual:
		venv\Scripts\activate.bat
		octoprint serve



