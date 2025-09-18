from smbus import SMBus

ADDR = 0x0C
WHO_AM_I = 0x01  # AK09918C WHO_AM_I
EXPECT = 0x10    # dovrebbe rispondere 0x10

bus = SMBus(1)
try:
    who = bus.read_byte_data(ADDR, WHO_AM_I)
    print("WHO_AM_I:", hex(who))
except Exception as e:
    print("Errore:", e)
bus.close()

