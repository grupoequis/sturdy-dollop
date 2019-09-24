    	#!/usr/bin/env python
# -*- coding: utf-8 -*-
 

"""tftp-client.
Usage:
  tftp-client.py get <filename> [[-s | -b ] --mode=<mode>]
"""
import argparse
from socket import *
from struct import pack
from struct import unpack
mode_list = {'unknown': 0,'netascii': 1,'octet': 2,'mail': 3}

error_message = {
    0: "Not defined, see error message (if any).",
    1: "File not found.",
    2: "Access violation.",
    3: "Disk full or allocation exceeded.",
    4: "Illegal TFTP operation.",
    5: "Unknown transfer ID.",
    6: "File already exists.",
    7: "No such user."
}

sock = socket(AF_INET, SOCK_DGRAM,0)
server_address = ('localhost', 69)
ackn = 0
port = 69
sent_address = ('localhost',69)


def binary_rrq(filename, mode):
	request = bytearray()
	# READ REQUEST
	request.append(0)	
	request.append(1)	
	filename = bytearray(filename.encode('utf-8'))
	request += filename	
	request.append(0)
	request += bytearray(bytes(mode, 'utf-8'))
	request.append(0)
	sock.sendto(request, server_address)


def struct_rrq(filename, mode):
    formatter = '>h{}sB{}sB'  # { > - Big Endian, h - short , s - char, B - 1 byte }
    formatter = formatter.format(len(filename), len('netascii'))
    request = pack(formatter, 1, bytes(filename, 'utf-8'), 0, bytes(mode, 'utf-8'), 0)
    sock.sendto(request, server_address)


def sendACK(ack_data, server):
	ack = bytearray(ack_data)
	ack[0] = 0	
	ack[1] = 4
	sock.sendto(ack, server)

def console():
	print("tftp>",end='')
	cmd = input()
	cmds = cmd.split(" ")
	if(cmds[0] == "put"):
		put(cmds[1])
def put(filename):
	print('sending file')
	request = bytearray()
	request.append(0)
	request.append(2)
	request += bytearray(filename.encode('utf-8'))
	request.append(0)
	request += bytearray("netascii".encode('utf-8'))
	request.append(0)
	sock.sendto(request,server_address)
	res = waitack()
	if(res != 'ack'):
		print("error sending file")
	f=open(filename, "r")
	filebytes = bytearray(f.read().encode('utf-8'))
	lenght = len(filebytes)
	i = 0
	n = 0
	while i < lenght:
		request = bytes.fromhex("0003%04x" % ackn )
		sock.sendto(request + filebytes[i:i+512],sent_address)
		res = waitack()
		if(res != 'ack'):
			print('error sending file')
			break

		i +=512
		n +=1
def waitack():
	global ackn
	global sent_address
	while True:
		data, address = sock.recvfrom(4096)
		sent_address = address
		ack = 4
		results = unpack('>'+'h'*(len(data)//2),data)
		print("ack: %d %d" % (results[0],results[1]))
		if ack == results[0] and ackn == results[1]:
			ackn += 1
			return "ack"



def error(data):
	opcode = data[:2]
	return int.from_bytes(opcode, byteorder='big') == 5

def main():
	console()
	print("terminando")
	parser = argparse.ArgumentParser()
	parser.add_argument("-b", "--binary", help="request built with bytearray", action="store_true")
	parser.add_argument("-s", "--struct", help="request built with struct", action="store_true")
	parser.add_argument("-f", "--file", help="file")
	parser.add_argument("-mode", "--mode", help="TFTP transfer mode")
	args = parser.parse_args()
	parser.print_help()
 
	# check arguments
	if args.binary:
	    print ("En bytearray")
	if args.struct:
	    print ("En struct")
	if args.file:
	    print ("Filename: ", args.file)
	if args.mode:
	    print ("Mode: ", args.mode)

	mode = args.mode
	if mode is not None:
		if mode.lower() not in mode_list.keys():
			print ("Unknown mode. Mode: netascci")		    
			mode = "netascii"
	else:
		mode = "netascii"
	
	if args.binary:
		binary_rrq(args.file, mode)
	elif args.struct:
		struct_rrq(args.file, mode)
	else: 	
		struct_rrq(args.file, mode)

	file = open(args.file, "wb")
	while True:
		# Wait for the data from the server
		data, server = sock.recvfrom(600)
		if error(data):
			error_code = int.from_bytes(data[2:4], byteorder='big')
			print(error_message[error_code])
			break
		sendACK(data[0:4], server)
		file.write(data[4:])
		# Last block
		if len(data) < 516:
		    	break
if __name__ == '__main__':
    main()
