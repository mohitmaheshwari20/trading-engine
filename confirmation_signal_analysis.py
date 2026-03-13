import re
from collections import Counter

with open(r"C:\Projects\trading_engine\logs\confirmation_signal.txt", "r") as f:
    lines = f.read()

fail_price  = lines.count("FAIL: Price below EMA20")
fail_adx    = lines.count("FAIL: ADX not rising")
fail_volume = lines.count("FAIL: Volume below average")
confirmed   = lines.count("CONFIRMED")

print(f"Price below EMA20 : {fail_price}")
print(f"ADX not rising    : {fail_adx}")
print(f"Volume below avg  : {fail_volume}")
print(f"Confirmed         : {confirmed}")