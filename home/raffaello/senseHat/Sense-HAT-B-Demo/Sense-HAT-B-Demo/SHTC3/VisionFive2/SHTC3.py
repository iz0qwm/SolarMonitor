#!/usr/bin/python
'''
Please make sure the sense HAT(B) is connected to the correct pins.
The following table describes how to connect the Sense HAT(B) to the 40-pin header.
--------------------------------------------
__Sense HAT (B)___Pin Number_____Pin Name
    3V3             1            3.3 V Power
    GND             9              GND
    SDA             3            I2C SDA
    SCL             5            I2C SCL
--------------------------------------------
'''

import sys
import struct
import fcntl
import os
import math
import time
import VisionFive.i2c as I2C
import VisionFive.boardtype as board_t

SHTC3_I2C_ADDRESS = 0x70
I2C_SLAVE = 0x0703
#I2C_DEVICE = "/dev/i2c-1"
#I2C_DEVICE = "/dev/i2c-0"

##Commands
cmd_dict = {
"SHTC3_WakeUp": 		0x3517,
"SHTC3_Sleep": 			0xB098,
"SHTC3_NM_CE_ReadTH": 	0x7CA2,
"SHTC3_NM_CE_ReadRH": 	0x5C24,
"SHTC3_NM_CD_ReadTH": 	0x7866,
"SHTC3_NM_CD_ReadRH": 	0x58E0,
"SHTC3_LM_CE_ReadTH": 	0x6458,
"SHTC3_LM_CE_ReadRH": 	0x44DE,
"SHTC3_LM_CD_ReadTH": 	0x609C,
"SHTC3_LM_CD_ReadRH": 	0x401A,
"SHTC3_Software_RES": 	0x401A,
"SHTC3_ID": 			0xEFC8,
"CRC_POLYNOMIAL":       0x131,
}


def SHTC3_CheckCrc(data, len, checksum):
    crc = 0xff
    for byteCtr in range(0, len):
        crc ^= data[byteCtr]
        for bit in range(8, 0, -1):
            if(crc & 0x80):
                crc = (crc << 1) ^ cmd_dict["CRC_POLYNOMIAL"]
            else:
                crc = crc << 1
    if (crc != checksum):
        return 1
    else:
        return 0

def SHTC3_WriteCommand(cmd):
    buf0 =  (cmd >> 8)& 0xff
    buf1 = cmd & 0xff
    buf = [buf0, buf1]
    I2C.write(buf)

def SHTC3_WAKEUP():
    SHTC3_WriteCommand(cmd_dict["SHTC3_WakeUp"])
    time.sleep(0.03)

def SHTC3_SLEEP():
    SHTC3_WriteCommand(cmd_dict["SHTC3_Sleep"])

def SHTC_SOFT_RESET():
    SHTC3_WriteCommand(cmd_dict["SHTC3_Software_RES"])
    time.sleep(0.03)

def getdata():
    time.sleep(0.02)
    buf_list = I2C.read(3)
    checksum = buf_list[2]
    DATA = 0
    if (not SHTC3_CheckCrc(buf_list, 2, checksum)):
        DATA = (buf_list[0] << 8 | buf_list[1])
    return DATA

def SHTC3_Read_DATA():
    SHTC3_WriteCommand(cmd_dict["SHTC3_NM_CD_ReadTH"])
    TH_DATA = getdata()
    SHTC3_WriteCommand(cmd_dict["SHTC3_NM_CD_ReadRH"])
    RH_DATA = getdata()
    TH_DATA = 175 * TH_DATA /65536.0 -45.0   #Calculate the temperature value.
    RH_DATA = 100 * RH_DATA / 65536.0        #Calculate the humidity value.
    DATA = [TH_DATA,RH_DATA]
    return DATA

def getTem():
    SHTC3_WriteCommand(cmd_dict["SHTC3_NM_CD_ReadTH"])
    TH_DATA = getdata()
    TH_DATA = 175 * TH_DATA /65536.0 -45.0   #Calculate the temperature value.
    return TH_DATA

def getHum():
    SHTC3_WriteCommand(cmd_dict["SHTC3_NM_CD_ReadRH"])
    RH_DATA = getdata()
    RH_DATA = 100 * RH_DATA / 65536.0        #Calculate the humidity value.
    return RH_DATA

def main():
    #Determining cpu Type: 1 means visionfive1; 2 means visionfive 2 
    vf_t = board_t.boardtype()
    if vf_t == 1:
        I2C_DEVICE = "/dev/i2c-1"
    elif vf_t == 2:
        I2C_DEVICE = "/dev/i2c-0"
    else:
        print('This module can only be run on a VisionFive board!')
        return 0

    #Open the Sense HAT by I2C.
    ret = I2C.open(I2C_DEVICE, SHTC3_I2C_ADDRESS)
    if (ret < 0):
        return 0


    SHTC_SOFT_RESET()
    i = 0
    while i < 7:
        Temp = getTem()
        Hum = getHum()
        SHTC3_SLEEP()
        SHTC3_WAKEUP()
        print("Temperature = {:.2f}°C , Humidity = {:.2f} %\n".format(Temp, Hum))
        i = i + 1

    I2C.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())



