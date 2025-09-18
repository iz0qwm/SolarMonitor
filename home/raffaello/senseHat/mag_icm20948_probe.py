#!/usr/bin/env python3
# Probe magnetometro su ICM-20948 (Sense HAT B - Waveshare)
# Tenta libreria Waveshare o Pimoroni; fallback "raw" se già abilitato dal demo.

import time, math

def _read_with_waveshare():
    try:
        # Nome tipico del file della demo: ICM20948.py nella stessa cartella
        from ICM20948 import ICM20948
        icm = ICM20948()
        # molte demo espongono funzioni simili a queste:
        #   icm.icm20948_Gyro_Accel_Read()
        #   mx, my, mz = icm.icm20948_Mag_Read()
        mx, my, mz = icm.icm20948_Mag_Read()
        return ("waveshare", mx, my, mz)
    except Exception:
        return None

def _read_with_pimoroni():
    try:
        # pacchetto "icm20948" (Pimoroni)
        from icm20948 import ICM20948
        icm = ICM20948()
        # Pimoroni: microtesla
        mx, my, mz = icm.read_magnetometer_data()
        return ("pimoroni", mx, my, mz)
    except Exception:
        return None

def _read_fallback_raw():
    # Fallback minimale: legge i registri dati mag se già abilitato dall'IMU.
    # Solo best-effort: non abilita il bus secondario né il power-on del mag.
    try:
        from smbus import SMBus
        BUS = 1
        ADDR = 0x68
        # Bank select
        def bank(bus, b):
            bus.write_byte_data(ADDR, 0x7F, b<<4)
        bus = SMBus(BUS)
        try:
            bank(bus, 0)  # user bank 0
            # EXT_SLV_SENS_DATA_00..05
            # se il controller I2C master interno è configurato, qui trovi X,Y,Z LSB/MSB del magnetometro.
            d = [bus.read_byte_data(ADDR, 0x3B + i) for i in range(6)]
            # AKM tipicamente little-endian: L,H per ogni asse
            def to_i16(lo, hi):
                val = (hi<<8)|lo
                return val-65536 if val>32767 else val
            x = to_i16(d[0], d[1])
            y = to_i16(d[2], d[3])
            z = to_i16(d[4], d[5])
            # scala ignota → restituiamo counts grezzi
            return ("raw", x, y, z)
        finally:
            bus.close()
    except Exception:
        return None

def main():
    for reader in (_read_with_waveshare, _read_with_pimoroni, _read_fallback_raw):
        res = reader()
        if res:
            src, x, y, z = res
            norm = math.sqrt(x*x+y*y+z*z)
            print({"source": src, "mx": x, "my": y, "mz": z, "norm": norm})
            return
    print({"error": "no magnetometer data (lib non trovata o mag non abilitato)"})

if __name__ == "__main__":
    main()

