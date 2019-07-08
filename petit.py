#!/usr/bin/env python

#from multiprocessing import Process, Value, Array

import io
import datetime
import time

import picamera
from PIL import Image
import zbar
import cv2
import numpy as np

import pymysql

import os
import socket
import psutil
from subprocess import Popen, PIPE

import paho.mqtt.client as mqtt

import serial

import threading


# configure the serial connections (the parameters differs on the device you are connecting to)
print('Pet-It > Serial port initialization.')
print('Pet-It > Serial port baudrate is 115200bps.')
COM1 = serial.Serial(
	port = '/dev/ttyAMA0',
	baudrate = 115200,
	parity = serial.PARITY_NONE,
	stopbits = serial.STOPBITS_ONE,
	bytesize = serial.EIGHTBITS,
	timeout = 1
)


#
################################################################################
#
#	Initialize Serial Port
#
def SerialInit(baudrate) :
	print('Pet-It > Serial port baudrate is 115200bps.')
	# serial init
	COM1 = serial.Serial(
		port = '/dev/ttyAMA0',
		baudrate = baudrate,
		parity = serial.PARITY_NONE,
		stopbits = serial.STOPBITS_ONE,
		bytesize = serial.EIGHTBITS,
		timeout = 1
	)


#
################################################################################
#
#	Transmit Serial Data
#
def SerialTransmit(data_type, data1, data2) :
	tx_buffer = [ '$', 0, 0, 0, 0, '\r' ]

	tx_buffer[1] = data_type	# 'S'
	tx_buffer[2] = data1
	tx_buffer[3] = data2
	tx_buffer[4] = int(tx_buffer[1]) ^ int(tx_buffer[2]) ^ int(tx_buffer[3])

	COM1.write(bytearray(tx_buffer[0:6]))


#
################################################################################
#
#	QR code Detect & Decode
#
def DecodeQrcode() :
	while True :
		# Create the in-memory stream
		stream = io.BytesIO()

		print('Pet-It > Camera operation.')
		with picamera.PiCamera() as camera:
			#camera.start_preview()
			time.sleep(2)
			camera.capture(stream, format='jpeg')

		print('Pet-It > Image processing.')
		#"Rewind" the stream to the beginning so we can read its content
		stream.seek(0)
		pil = Image.open(stream)

		imgGauss = cv2.GaussianBlur(np.asarray(pil), (3,3), 0)
		gray = cv2.cvtColor(imgGauss, cv2.COLOR_RGB2GRAY)
		fm = cv2.Laplacian(gray, cv2.CV_64F).var()

#		print "%d" % fm
#		if fm < 10 :
#			continue

		print('Pet-It > Scanning QRcode.')
		# create a reader
		scanner = zbar.ImageScanner()

		# configure the reader
		scanner.parse_config('enable')

		pil = pil.convert('L')
		width, height = pil.size
		raw = pil.tobytes()

		# wrap image data
		image = zbar.Image(width, height, 'Y800', raw)

		# scan the image for barcodes
		scanner.scan(image)

		# extract results
		for symbol in image:
			if 'QRCODE' in str(symbol.type) :
				print('Pet-It > decoded', symbol.type, 'symbol', '"%s"' % symbol.data)

				result = symbol.data

				del(image)
				return result
			else :
				continue

		# clean up
		del(image)
		pass

#
################################################################################
#
#	Extract serial from cpuinfo file
#
def ReadCPUID() :
	cpuid = "0000000000000000"
	info = open('/proc/cpuinfo','r')
	for line in info:
		if line[0:6]=='Serial':
			cpuid = line[10:26]
	info.close()

	return cpuid


#
################################################################################
#
#	Audio Stream
#
def AudioThread() :
	global audio_flag, audioi_stream
	global phone_no

	cpuid = ReadCPUID()

	while True :
		if audio_flag == 1 :
			audio_flag = 2
#			audio_stream = Popen('mplayer -ao alsa rtsp://211.38.86.93:1935/live/%s-%s' % (cpuid, phone_no), stdin=PIPE, shell=True)
			time.sleep(10)
		elif audio_flag == 3 :
			audio_stream.communicate('q')
			time.sleep(1)
			audio_flag = 0


#
################################################################################
#
#	MQTT
#
def filesave_history(feed_type, feed_qty, user_phone) :
	now = time.localtime()

	try :
		fb = open('/home/pi/petit/feed_data/%d%02d%02d' % (now.tm_year, now.tm_mon, now.tm_mday), 'rb')
		file_ok = 1
		payload = fb.read()
		fb.close()
	except IOError :
		file_ok = 0
		print('MQTT > %d%02d%02d file not found' % (now.tm_year, now.tm_mon, now.tm_mday))
		print('MQTT > %d%02d%02d file create' % (now.tm_year, now.tm_mon, now.tm_mday))
	finally :
		fb = open('/home/pi/petit/feed_data/%d%02d%02d' % (now.tm_year, now.tm_mon, now.tm_mday), 'wb+')
		save_data = [now.tm_year - 2000, now.tm_mon, now.tm_mday, now.tm_hour, now.tm_min, feed_type, feed_qty]
		fb.write(bytearray(save_data))
		fb.write(user_phone)
		if file_ok == 1 :
			fb.write(bytearray(payload))
		fb.close()


def filesave_feeddb(feed_type, feed_qty) :
	now = time.localtime()

	if feed_type == 0 :
		fb = open('/home/pi/petit/feed_db/temp', 'wb')
		save_data = [now.tm_year - 2000, now.tm_mon, now.tm_mday, now.tm_hour, now.tm_min, feed_qty]
		fb.write(bytearray(save_data))
		fb.close()

	elif feed_type == 1 :
		fb = open('/home/pi/petit/feed_db/temp', 'ab+')
		save_data = [now.tm_hour, now.tm_min, feed_qty]
		fb.write(bytearray(save_data))
		fb.seek(0)
		temp_data = fb.read()
		fb.close()

		try :
			fb = open('/home/pi/petit/feed_db/%d%02d%02d' % (now.tm_year, now.tm_mon, now.tm_mday), 'rb')
			file_ok = 1
			payload = fb.read()
			fb.close()
		except IOError :
			file_ok = 0
			print('MQTT > %d%02d%02d file not found' % (now.tm_year, now.tm_mon, now.tm_mday))
			print('MQTT > %d%02d%02d file create' % (now.tm_year, now.tm_mon, now.tm_mday))
		finally :
			fb = open('/home/pi/petit/feed_db/%d%02d%02d' % (now.tm_year, now.tm_mon, now.tm_mday), 'wb')
			fb.write(bytearray(temp_data))
			if file_ok == 1 :
				fb.write(bytearray(payload))
			fb.close()


def on_subscribe(mosquitto, obj, mid, granted_qos) :
	print('MQTT > Subscribed: ' + str(mid) + ' ' + str(granted_qos))


# The callback for when the client receives a CONNACK response from the server.
def on_connect(mosquitto, obj, flags, rc) :
	cpuid = ReadCPUID()
	mosquitto.subscribe('$open-it/pet-it/%s/order' % cpuid, 0)
	mosquitto.publish('$open-it/pet-it/%s/alive' % cpuid, 'connected', 1, True)
	print('MQTT > rc: ' + str(rc))


# The callback for when a PUBLISH message is received from the server.
def on_message(mosquitto, obj, msg) :
	global video_stream, run_video, run_feeder, run_voice, run_audio
#	global audio_stream
	global tx_buffer
	global feed_qty, user_phone
	global phone_no, audio_flag

	print('recv ' + msg.topic + '(' + str(msg.qos) + ') : ' + str(msg.payload))

	cpuid = ReadCPUID()

	if 'request video' in str(msg.payload) :
		payload = msg.payload.split('/')

		if run_video == 0 :
			print('Pet-It > Start video stream.')
			SerialTransmit(0x53, 0x31, 0x31)

#			stream = Popen('gst-launch-1.0 -v rpicamsrc bitrate=2097152 preview=false rotation=180 sensor-mode=5 \
#						! video/x-h264,width=640,height=360,framerate=30/1,profile=high \
#						! h264parse \
#						! flvmux \
#						! rtmpsink location="rtmp://211.38.86.93:1935/live/%s"' % cpuid, shell=True)
#			mosquitto.publish('$open-it/pet-it/%s/status' % cpuid, 'start video', 1)

			video_stream = Popen('gst-launch-1.0 rpicamsrc bitrate=2097152 preview=false rotation=0 sensor-mode=5 \
							! video/x-h264,width=640,height=360,framerate=30/1,profile=high \
							! h264parse \
							! flvmux name=mux alsasrc \
							! audioresample \
							! audio/x-raw,rate=44100 \
							! queue \
							! voaacenc bitrate=32000 \
							! queue \
							! mux. mux. \
							! rtmpsink location="rtmp://211.38.86.93:1935/live/%s"' % cpuid, shell=True)
			time.sleep(2)
#			audio_stream = Popen('mplayer rtsp://211.38.86.93:1935/live/%s-%s' % (cpuid, payload[1]), stdin=subprocess, PIPE, stderr=subprocess, PIPE, close_fds=True)
#			time.sleep(2)
			phone_no = payload[1]
			audio_flag = 1
			time.sleep(2)
			run_video = 1;
		else :
			time.sleep(2)
			#audio_stream[run_video] = Popen('omxplayer -b -o alsa:hw:0,0 rtsp://211.38.86.93:1935/live/%s-audio' % payload[1], shell=True)

			run_video += 1;

		mosquitto.publish('$open-it/pet-it/%s/status' % cpuid, 'start video', 1)
		print('Pet-It > Video stream count : %s' % run_video)

	elif 'stop video' in str(msg.payload) :
		payload = msg.payload.split('/')

		if run_video == 1 :
			run_video = 0;

			print('Pet-It > Stop video stream.')
			SerialTransmit(0x53, 0x31, 0x30)

			parent = psutil.Process(video_stream.pid)
			for child in parent.children(recursive = True) :
				child.kill()
			parent.kill()

			if audio_flag == 2 :
				audio_flag = 3

			#audio_stream.stdin.write('q')
#			parent = psutil.Process(audio_stream.pid)
#			for child in parent.children(recursive = True) :
#				child.kill()
#			parent.kill()

		if run_video > 0 :
			run_video -= 1;
			print('Pet-It > Remaining video stream count : %s' % run_video)

	elif 'feeder' in str(msg.payload) :
		if run_feeder == 0 :
			feed_qty = msg.payload[6]
			user_phone = msg.payload[7:]
			print('Remote Feeder : %s %s' % (user_phone, feed_qty))

			if len(user_phone) == 11 :
				SerialTransmit(0x46, int(feed_qty) // 10 + 0x30, int(feed_qty) % 10 + 0x30)
#				tx_buffer[1] = 0x46
#				tx_buffer[2] = int(feed_qty) // 10 + 0x30
#				tx_buffer[3] = int(feed_qty) % 10 + 0x30
#				tx_buffer[4] = int(tx_buffer[1]) ^ int(tx_buffer[2]) ^ int(tx_buffer[3])

				run_feeder = 1
			else :
				print('No User Phone Number...')

	elif 'voice' in str(msg.payload) :
		if run_voice == 0 :
			print('Pet-It > Playback voice.')
			run_voice = 1

	elif 'reservation request' in str(msg.payload) :
		try :
			fb = open('/home/pi/petit/config/reservation_table', 'rb')
			reservation_table = fb.read()
			mosquitto.publish('$open-it/pet-it/%s/status' % cpuid, reservation_table, 1)
			fb.close()
		except IOError :
			mosquitto.publish('$open-it/pet-it/%s/status' % cpuid, '', 1)

	elif 'history request' in str(msg.payload) :
		fb_save = open('/home/pi/petit/feed_data/trans_history', 'wb+')
		now = datetime.date.today()

		for i in range(0, 4) :
			try :
				date = now - datetime.timedelta(days=i)
				fb = open('/home/pi/petit/feed_data/%d%02d%02d' % (date.year, date.month, date.day), 'rb')
				payload = fb.read()
				fb_save.write(bytearray(payload))
				fb.close()
			except IOError :
				print('Pet-It > %d%02d%02d file not found' % (date.year, date.month, date.day))

		try :
			date = now - datetime.timedelta(days=4)
			fb = open("/home/pi/petit/feed_data/%d%02d%02d" % (date.year, date.month, date.day), 'rb')
			payload = fb.read()
			fb_save.write(bytearray(payload))
			fb.close()
		except IOError :
			print("Pet-It > %d%02d%02d file not found" % (date.year, date.month, date.day))
		finally :
			fb_save.seek(0)
			payload = fb_save.read()
			fb_save.close()
			mosquitto.publish("$open-it/pet-it/%s/status" % cpuid, payload, 1)

		date = now - datetime.timedelta(days=5)
		if os.path.exists('/home/pi/petit/feed_data/%d%02d%02d' % (date.year, date.month, date.day)) == True :
			os.remove('/home/pi/petit/feed_data/%d%02d%02d' % (date.year, date.month, date.day))

	elif 'feeddb request' in str(msg.payload) :
		fb_save = open('/home/pi/petit/feed_db/trans_feeddb', 'wb+')
		now = datetime.date.today()

		for i in range(0, 29) :
			try :
				date = now - datetime.timedelta(days=i)
				fb = open('/home/pi/petit/feed_db/%d%02d%02d' % (date.year, date.month, date.day), 'rb')
				payload = fb.read()
				fb_save.write(bytearray(payload))
				fb.close()
			except IOError :
				print('Pet-It > %d%02d%02d file not found' % (date.year, date.month, date.day))

		try :
			date = now - datetime.timedelta(days=29)
			fb = open("/home/pi/petit/feed_db/%d%02d%02d" % (date.year, date.month, date.day), 'rb')
			payload = fb.read()
			fb_save.write(bytearray(payload))
			fb.close()
		except IOError :
			print("Pet-It > %d%02d%02d file not found" % (date.year, date.month, date.day))
		finally :
			fb_save.seek(0)
			payload = fb_save.read()
			fb_save.close()
			mosquitto.publish("$open-it/pet-it/%s/status" % cpuid, payload, 1)

		date = now - datetime.timedelta(days=30)
		if os.path.exists('/home/pi/petit/feed_db/%d%02d%02d' % (date.year, date.month, date.day)) == True :
			os.remove('/home/pi/petit/feed_db/%d%02d%02d' % (date.year, date.month, date.day))

	else :
		reservation_data = msg.payload
		fb = open('/home/pi/petit/config/reservation_table', 'wb+')
		fb.write(bytearray(reservation_data[:]))
		fb.close()


def on_publish(mosquitto, obj, mid):
	print('MQTT > Pub : mid :' + str(mid))


def on_log(mosquitto, obj, level, string):
	print('MQTT > log - ' + string)


#
################################################################################
#
#	Insert DB server
#
#def InsertDB(phone_number, cpuid, master_password, token_string) :
def InsertDB(phone_number, cpuid, master_password) :
	conn = pymysql.connect(host='211.38.86.93',
					user='root',
					password='niceduri',
					db='Pet-it',
					charset='utf8')
	try :
		with conn.cursor() as cursor :
#			sql = 'INSERT INTO Manager(P_NUM, GUID, PW, TOKEN) VALUES (%s, %s, %s, %s)'
#			cursor.execute(sql, (phone_number, cpuid, master_password, token_string))
			sql = 'INSERT INTO Manager(P_NUM, GUID, PW) VALUES (%s, %s, %s)'
			cursor.execute(sql, (phone_number, cpuid, master_password))
			conn.commit()
			print(cursor.lastrowid)
	finally :
		conn.close()

	return cursor.lastrowid


#
################################################################################
#
#	Select DB server
#
def SelectDB(phone_number, cpuid) :
	conn = pymysql.connect(host='211.38.86.93',
					user='root',
					password='niceduri',
					db='Pet-it',
					charset='utf8')
	try :
		with conn.cursor() as cursor :
			sql = 'SELECT * FROM Manager WHERE P_NUM = %s and GUID = %s'
			cursor.execute(sql, (phone_number, cpuid))
			result = cursor.fetchone()
			print(result)
	finally :
		conn.close()

	return result


#
################################################################################
#
#	Delete DB server
#
def DeleteDB(cpuid) :
	conn = pymysql.connect(host='211.38.86.93',
					user='root',
					password='niceduri',
					db='Pet-it',
					charset='utf8')
	try :
		with conn.cursor() as cursor :
			sql = 'DELETE FROM Manager WHERE GUID = %s'
			cursor.execute(sql, (cpuid,))
			conn.commit()
	finally :
		conn.close()


#
################################################################################
#
#	Check WI-fi connection
#
def CheckWifi() :
	s = None

	s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

	try:
		s.connect(('8.8.8.8', 80))
		ip = s.getsockname()[0]
	except socket.error as msg:
		s.close()
		s = None

	if s is None:
		return s

	s.close()
	return ip


#
################################################################################
#
#	Update /etc/wpa_supplicant/wpa_supplicant.conf
#
def ConnectionWlan(ssid, password) :
	print('Pet-It > Update wpa passpharse.')
	os.system('wpa_passphrase %s %s | sudo tee -a /etc/wpa_supplicant/wpa_supplicant.conf > /dev/null' %(ssid, password))
	os.system('sudo ifconfig wlan0 down')
	while 1 :
		if CheckWifi() is None :
			break
	print('Pet-It > Connecting Wi-fi.')
	os.system("sudo ifconfig wlan0 up")
	while 1 :
		if CheckWifi() is not None :
			print('Pet-It > My IP is ' + CheckWifi())
			break


#
################################################################################
#
#	Auto Feeder CHeck
#
def AutoFeeder(reservation_data) :
	global feed_qty, run_feeder

	if run_feeder == 0 :
		now = time.localtime()
		if now.tm_min == 0 : # and (now.tm_sec == 0) :
			if now.tm_hour == 0 :
				hour = 23
			else :
				hour = now.tm_hour - 1

			if now.tm_wday == 6 :
				wday = 0
			else :
				wday = now.tm_wday + 1

			if reservation_data[hour * 2] & (0x01 << wday) :
				feed_qty = reservation_data[(hour * 2) + 1]
				print('Pet-It > [%d/%d %d:%d] Reservation feed : %d' % (now.tm_mon, now.tm_mday, now.tm_hour, now.tm_min, feed_qty))
				SerialTransmit(0x41, int(feed_qty) // 10 + 0x30, int(feed_qty) % 10 + 0x30)

#				tx_buffer[1] = 0x41
#				tx_buffer[2] = int(feed_qty) // 10 + 0x30
#				tx_buffer[3] = int(feed_qty) % 10 + 0x30
#				tx_buffer[4] = int(tx_buffer[1]) ^ int(tx_buffer[2]) ^ int(tx_buffer[3])

				run_feeder = 1


#
################################################################################
#
#	Main Routine
#
if __name__ == '__main__' :
	global run_video, run_feeder, run_voice, run_audio
	global feed_qty, user_phone
	global audio_flag

	register = 0
	# Read CPU GUID
	cpuid = ReadCPUID()

#	print('Pet-It > Serial port initialization.')
#	SerialInit(115200)
	SerialTransmit(0, 0, 0)

	print('Pet-It > Check register file.')
	# 1'st Register
	if os.path.exists('/home/pi/petit/config/register') == False :
		read_qr = 1
	else :
		with open('/home/pi/petit/config/register', 'r') as fb :
			qrcode = fb.read()
			if len(qrcode) :
				read_qr = 0
			else :
				read_qr = 1

	if read_qr == 1 :
		print('Pet-It > PetIt is factory reset state.')
		SerialTransmit(0x53, 0x30, 0x30)

		print('Pet-It > Read QRcode.')
		qrdata = DecodeQrcode()

		print('Pet-It > Make register file.....')
		os.mkdir('/home/pi/petit/config')
		with open('/home/pi/petit/config/register', 'w') as qrcode :
			qrcode.write(qrdata)

		print('Pet-It > QRcode Split.')
		# QR code Data Split
		register_data = qrdata.split('/')

		wifi_ssid = register_data[0]
		wifi_password = register_data[1]
		master_password = register_data[2]
		phone_number = register_data[3]
#		token_string = register_data[4]

		# Read CPU GUID
#		cpuid = ReadCPUID()

		print('Pet-It > WiFi ssid = %s' % wifi_ssid)
		print('Pet-It > Wifi password = %s' % wifi_password)
		print('Pet-It > Master password = %s' % master_password)
		print('Pet-It > Phone Number = %s' % phone_number)
#		print('Pet-It > Token string = %s' % token_string)
		print('Pet-It > CPUID = %s' % cpuid)

		print('Pet-It > Update Wi-fi info & Connection Wi-fi.')
		# Update wifi connection file
		ConnectionWlan(wifi_ssid, wifi_password)

		print('Pet-It > Update DB server.')
		if SelectDB(phone_number, cpuid) :
			print('Pet-It > %s & %s' %(phone_number, cpuid), 'exist!')
		else :
			print('Pet-It > Register with new DB - %s & %s' %(phone_number, cpuid))
			InsertDB(phone_number, cpuid, master_password)
#			InsertDB(phone_number, cpuid, master_password, token_string)

		print('Pet-It > Make reservation table.')
		reservation_data = [0] * 48
		fb = open("/home/pi/petit/config/reservation_table", 'wb+')
		fb.write(bytearray(reservation_data[:]))
		fb.close()

		register = 1
	else :
		print('Pet-It > Read reservation table.')
		fb = open('/home/pi/petit/config/reservation_table', 'rb')
		reservation_data = bytearray(fb.read())

		fb.close()

		print('Pet-It > Read Register file.')
		fb = open('/home/pi/petit/config/register', 'r')
		qrdata = fb.read()

		register_data = qrdata.split('/')

		wifi_ssid = register_data[0]
		wifi_password = register_data[1]
		master_password = register_data[2]
		phone_number = register_data[3]
#		token_string = register_data[4]

		fb.close()


	print('Pet-It > Reservation table is %s' % reservation_data[0:])

	# Make feed data directory
	if os.path.isdir('/home/pi/petit/feed_data') == False :
		print('Make feed_data directory.....')
		os.mkdir('/home/pi/petit/feed_data')

	if os.path.isdir('/home/pi/petit/feed_db') == False :
		print('Make feed_db directory.....')
		os.mkdir('/home/pi/petit/feed_db')

	print('Pet-It > Initialize MQTT.')
	# MQTT
	petit_mqtt = mqtt.Client()

	# Assign event callbacks
	petit_mqtt.on_message = on_message
	petit_mqtt.on_connect = on_connect
	petit_mqtt.on_publish = on_publish
	petit_mqtt.on_subscribe = on_subscribe
	petit_mqtt.on_log = on_log

	print('Pet-It > Connect to MQTT broker.')
	# MQTT broker Connect
	petit_mqtt.will_set('$open-it/pet-it/%s/alive' % cpuid, 'dead', 0, True)
	petit_mqtt.connect("211.38.86.93", 1883,  60)
	# Blocking call that processes network traffic, dispatches callbacks and
	# handles reconnecting.
	# Other loop*() functions are available that give a threaded interface and a
	# manual interface.
	print('Pet-It > Starting the MQTT client.')
	petit_mqtt.loop_start()

	print('Pet-It > Normal operation.')
	SerialTransmit(0x53, 0x31, 0x30)
#	tx_buffer[1] = 0x53	# 'S'
#	tx_buffer[2] = 0x31
#	tx_buffer[3] = 0x30
#	tx_buffer[4] = int(tx_buffer[1]) ^ int(tx_buffer[2]) ^ int(tx_buffer[3])
#	COM1.write(bytearray(tx_buffer[0:6]))

	if register == 1 :
		petit_mqtt.publish('$open-it/pet-it/%s/status' % phone_number, phone_number, 1)

	run_video = 0
	run_feeder = 0
	run_voice = 0
	run_audio = 0

	audio_flag = 0

	audio_thread = threading.Thread(target = AudioThread, args = ())
	audio_thread.start()

	rx_buffer = [ 0, 0, 0, 0, 0, 0 ]
	rx_count = 0
	rx_start = 0
	rx_parse = 0
	while True :
		AutoFeeder(reservation_data)

		sbuf = COM1.read(1)
		if sbuf :
			if rx_start == 0 :
				if sbuf == '$' :
					rx_buffer[0] = sbuf
					rx_count = 1
					rx_start = 1
			else :
				if sbuf == '\r' :
					rx_buffer[rx_count] = sbuf
#					print(bytearray(rx_buffer))
					rx_parse = 1
				else :
					rx_buffer[rx_count] = sbuf
					rx_count += 1

		if rx_parse == 1 :
			print('Pet-It > Receiving data from STM32F0 : %s' % rx_buffer[0:])

			if rx_buffer[1] == 'F' :
				if rx_buffer[2] == 'E' :
					print('Pet-It > Finish feeder operation.')
					run_feeder = 0
				else :
					print('Pet-It > Feeding...Save feed data')
					if (rx_buffer[2] == 'M') or (rx_buffer[2] == 'A') :
						user_phone = '00000000000'
					filesave_history(rx_buffer[2], rx_buffer[3], user_phone)
			elif rx_buffer[1] == 'V' :
				if run_voice == 2 :
					run_voice = 0
			elif rx_buffer[1] == 'L' :
#				qty = ord(rx_buffer[3])
				if rx_buffer[2] == 'B' :
					print('Pet-It > Feed amount before feeding.')
					filesave_feeddb(0, rx_buffer[3])
#					petit_mqtt.publish("$open-it/pet-it/%s/status" % cpuid, "before %d" % qty, 1)
				else :
					print('Pet-It > Feed amount after feeding.')
					filesave_feeddb(1, rx_buffer[3])
#					petit_mqtt.publish("$open-it/pet-it/%s/status" % cpuid, "after %d" % qty, 1)
			elif rx_buffer[1] == 'I' :
#				cpuid = ReadCPUID()
				print('Pet-It > Deleting [%s] table from DB server' % cpuid)
				DeleteDB(cpuid)

				print('Pet-It > Delete the [config] directory')
				os.system('rm -rf /home/pi/petit/config')
				time.sleep(3)

				print('Pet-It > Delete the [feed_data] directory')
				os.system('rm -rf /home/pi/petit/feed_data')
				time.sleep(3)

				print('Pet-It > Delete the [feed_db] directory')
				os.system('rm -rf /home/pi/petit/feed_db')
				time.sleep(3)

#				print('Pet-It > Delete the Wifi config file.')
#				os.system('sudo cp /home/pi/petit/wpa_supplicant.conf /etc/wpa_supplicant/')
#				time.sleep(3)

				SerialTransmit(0x53, 0x30, 0x30)
				print('Pet-It > Pet-It Reboot')
				os.system('sudo reboot')

			rx_buffer = [ 0, 0, 0, 0, 0, 0 ]
			rx_start = 0
			rx_parse = 0

		if run_feeder == 1 :
			print('Pet-It > Tx : Trans data to STM32F0.')
#			COM1.write(bytearray(tx_buffer[0:6]))
			run_feeder = 2
		if run_voice == 1 :
			run_voice = 2


	# Continue the network loop
	petit_mqtt.loop_stop()
	print('mqttc.loop_stop')
	petit_mqtt.disconnect()
