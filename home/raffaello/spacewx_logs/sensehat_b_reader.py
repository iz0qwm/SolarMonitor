#!/usr/bin/env python3
# Sense HAT B (Waveshare) adapter: SHTC3 (T/RH), LPS22HB (P/T), ICM20948 (mag)
# Dipendenze: lgpio (per SHTC3), smbus (per LPS22HB/ICM20948)

import math
import time

# --- SHTC3 (usa lgpio via demo ufficiale) ------------------------------------
try:
    import lgpio as _sbc
    from SHTC3 import SHTC3 as _SHTC3   # usa esattamente l'API del demo
    _HAS_SHTC3 = True
except Exception:
    _HAS_SHTC3 = False

# --- LPS22HB (usa smbus via demo ufficiale) ----------------------------------
try:
    from LPS22HB import LPS22HB as _LPS22HB
    import LPS22HB as _LPS22HB_mod      # per registri/bit nel demo
    _HAS_LPS22HB = True
except Exception:
    _HAS_LPS22HB = False

# --- ICM20948 (usa smbus via demo ufficiale) ---------------------------------
try:
    from ICM20948 import ICM20948 as _ICM20948
    from ICM20948 import Mag as _MAG_BUF  # lista globale aggiornata da icm20948MagRead()
    _HAS_ICM = True
except Exception:
    _HAS_ICM = False

# ---------------------------- SHTC3 ------------------------------------------

_SHTC3_DEV = None

def read_shtc3():
    """
    Ritorna (t_c, rh_pct) oppure (None, None) se non disponibile.
    Usa il driver del demo (lgpio) e le funzioni SHTC3_Read_TH/RH.
    """
    if not _HAS_SHTC3:
        return None, None
    global _SHTC3_DEV
    try:
        if _SHTC3_DEV is None:
            _SHTC3_DEV = _SHTC3(_sbc, 1, 0x70)  # bus=1, addr=0x70
        t = _SHTC3_DEV.SHTC3_Read_TH()   # °C  (demo: wake, cmd NM, CRC)  # :contentReference[oaicite:3]{index=3}
        h = _SHTC3_DEV.SHTC3_Read_RH()   # %RH (idem)                    # :contentReference[oaicite:4]{index=4}
        # Il demo ritorna 0 in caso di CRC error → normalizziamo a None
        t_c  = round(t, 2)  if t  != 0 else None
        rh_p = round(h, 1)  if h  != 0 else None
        return t_c, rh_p
    except Exception:
        return None, None

# ---------------------------- LPS22HB ----------------------------------------

_LPS22 = None

def read_lps22hb():
    """
    Ritorna (press_hpa, temp_c) oppure (None, None) se non disponibile.
    Implementa la stessa logica del demo: one-shot + STATUS + read OUT regs.
    """
    if not _HAS_LPS22HB:
        return None, None
    global _LPS22
    try:
        if _LPS22 is None:
            _LPS22 = _LPS22HB()  # istanzia SMBus(1) e reset + BDU=1 ODR=0      # :contentReference[oaicite:5]{index=5}
        # trigger one-shot
        _LPS22.LPS22HB_START_ONESHOT()                                          # :contentReference[oaicite:6]{index=6}
        time.sleep(0.02)
        # status & read
        st = _LPS22._read_byte(_LPS22HB_mod.LPS_STATUS)                         # :contentReference[oaicite:7]{index=7}
        p_hpa = None
        t_c   = None
        if st & 0x01:  # pressione pronta                                       # :contentReference[oaicite:8]{index=8}
            xl = _LPS22._read_byte(_LPS22HB_mod.LPS_PRESS_OUT_XL)
            l  = _LPS22._read_byte(_LPS22HB_mod.LPS_PRESS_OUT_L)
            h  = _LPS22._read_byte(_LPS22HB_mod.LPS_PRESS_OUT_H)
            raw = (h<<16)|(l<<8)|xl
            p_hpa = round(raw/4096.0, 2)                                        # :contentReference[oaicite:9]{index=9}
        if st & 0x02:  # temperatura pronta                                     # :contentReference[oaicite:10]{index=10}
            tl = _LPS22._read_byte(_LPS22HB_mod.LPS_TEMP_OUT_L)
            th = _LPS22._read_byte(_LPS22HB_mod.LPS_TEMP_OUT_H)
            t_c = round(((th<<8)|tl)/100.0, 2)                                  # :contentReference[oaicite:11]{index=11}
        return p_hpa, t_c
    except Exception:
        return None, None

# ---------------------------- ICM20948 MAG -----------------------------------

_ICM = None

def _icm_init():
    global _ICM
    if _ICM is not None:
        return True
    if not _HAS_ICM:
        return False
    try:
        _ICM = _ICM20948()
        # il demo abilita già AK09916 a 20 Hz nel costruttore                     # :contentReference[oaicite:12]{index=12}
        return True
    except Exception:
        _ICM = None
        return False

def read_icm20948_mag():
    """
    Ritorna (mx_counts, my_counts, mz_counts, norm_counts) oppure (None, ..).
    Usa icm20948MagRead() che popola la lista globale Mag nel modulo demo.
    """
    if not _icm_init():
        return None, None, None, None
    try:
        _ICM.icm20948MagRead()              # aggiorna Mag[0..2] con medie/segni  # :contentReference[oaicite:13]{index=13}
        mx, my, mz = _MAG_BUF[0], _MAG_BUF[1], _MAG_BUF[2]
        norm = math.sqrt(mx*mx + my*my + mz*mz)
        return int(mx), int(my), int(mz), float(f"{norm:.2f}")
    except Exception:
        return None, None, None, None

# ---------------------------- Quick self-test --------------------------------
if __name__ == "__main__":
    t, rh = read_shtc3()
    p, tt = read_lps22hb()
    mx,my,mz,n = read_icm20948_mag()
    print({
        "shtc3": {"t_c": t, "rh_pct": rh},
        "lps22hb": {"press_hpa": p, "temp_c": tt},
        "icm20948": {"mx": mx, "my": my, "mz": mz, "norm_counts": n}
    })

