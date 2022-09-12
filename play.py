import serial
import time

ser = serial.Serial("COM4", baudrate=9600, timeout=1)
print("Initial positions")
ser.write("6CP\r\n".encode())
time.sleep(0.5)
res = ser.readline().decode()
print(res)
ser.write("4CP\r\n".encode())
time.sleep(0.5)
res = ser.readline().decode()
print(res)
print("Switching 4-way valve...")
if "A" in res:
    ser.write("4GOB\r\n".encode())
elif "B" in res:
    ser.write("4GOA\r\n".encode())
time.sleep(0.5)
print("New positions")
ser.write("6CP\r\n".encode())
time.sleep(0.5)
res = ser.readline().decode()
print(res)
ser.write("4CP\r\n".encode())
time.sleep(0.5)
res = ser.readline().decode()
print(res)
