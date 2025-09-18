#!/usr/bin/env python3
# Lettura SHTC3 (addr 0x70) - temperatura e umidità
from smbus import SMBus
import time

ADDR = 0x70
CMD_WAKE   = 0x3517
CMD_SLEEP  = 0xB098
CMD_MEAS_N = 0x7866  # normal power, clock stretching disabled

def write_cmd(bus, cmd):
    bus.write_i2c_block_data(ADDR, (cmd>>8)&0xFF, [cmd & 0xFF])

def crc_ok(bytes2, crc):
    # SHTC3 CRC8 poly=0x31 init=0xFF
    poly = 0x31
    rem = 0xFF
    for b in bytes2:
        rem ^= b
        for _ in range(8):
            rem = ((rem<<1)&0xFF) ^ poly if (rem & 0x80) else (rem<<1)&0xFF
    return rem == crc

def read():
    bus = SMBus(1)
    try:
        write_cmd(bus, CMD_WAKE)
        time.sleep(0.001)
        write_cmd(bus, CMD_MEAS_N)
        time.sleep(0.015)
        data = bus.read_i2c_block_data(ADDR, 0x00, 6)
        t_raw = data[0:2]; t_crc = data[2]
        h_raw = data[3:5]; h_crc = data[5]
        if not (crc_ok(t_raw, t_crc) and crc_ok(h_raw, h_crc)):
            raise RuntimeError("CRC error")
        t_code = (t_raw[0]<<8)|t_raw[1]
        h_code = (h_raw[0]<<8)|h_raw[1]
        t_c = -45 + 175 * (t_code/65535.0)
        rh  = 100 * (h_code/65535.0)
        write_cmd(bus, CMD_SLEEP)
        return round(t_c,2), round(rh,1)
    finally:
        bus.close()

if __name__ == "__main__":
    print(dict(zip(["t_c","rh_pct"], read())))

