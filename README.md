# rap-robot


1. Download Raspbian from [raspberrypi](https://www.raspberrypi.org/downloads/raspbian/)
2. Install the thermal printer based on Adafruit tutorials [[1]](https://learn.adafruit.com/networked-thermal-printer-using-cups-and-raspberry-pi/connect-and-configure-printer),[[2]](https://learn.adafruit.com/instant-camera-using-raspberry-pi-and-thermal-printer/system-setup)

Libraries:

```bash
sudo apt-get update
sudo apt-get install libcups2-dev libcupsimage2-dev git build-essential cups system-config-printer
```

Custom Driver from Adafruit:

```bash
git clone https://github.com/adafruit/zj-58
cd zj-58
make
sudo ./install
```

Set up the defaul printer to be the thermal printer:

```bash
sudo lpadmin -p ZJ-58 -E -v serial:/dev/ttyUSB0?baud=9600 -m zjiang/ZJ-58.ppd
sudo lpoptions -d ZJ-58
```

3. Install tensorflow 1.3 compiled for Python 2.7 

```bash
git clone https://github.com/DeftWork/rpi-tensorflow.git
cd rpi-tensorflow
pip2 install tensorflow-1.3.0-cp27-none-linux_armv7l.whl
```

4. Python dependencies

```bash

pip install subprocess32 unidecode twython twilio pygame

```


