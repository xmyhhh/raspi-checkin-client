import serial
import time
import threading
import sys
import RPi.GPIO as GPIO

# Pin config
WAKE_PIN = 23
RST_PIN = 24

# Bool value definition
TRUE = 1
FALSE = 0

# Basic response message definition
ACK_SUCCESS = 0x00  # 操作成功
ACK_FAIL = 0x01  # 操作失败
ACK_FULL = 0x04  # 指纹数据库已满
ACK_NO_USER = 0x05  # 无此用户
ACK_USER_EXIST = 0x06  # 用户已存在
ACK_TIMEOUT = 0x08  # 采集超时

# User information definition
ACK_ALL_USER = 0x00
ACK_GUEST_USER = 0x01
ACK_NORMAL_USER = 0x02
ACK_MASTER_USER = 0x03
USER_MAX_CNT = 1000

# Command definition
CMD_HEAD = 0xF5
CMD_TAIL = 0xF5

# Init
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(WAKE_PIN, GPIO.IN)
GPIO.setup(RST_PIN, GPIO.OUT)
GPIO.setup(RST_PIN, GPIO.OUT, initial=GPIO.HIGH)
SLEEPING = 0
LOCK = threading.RLock()
DEVICE = serial.Serial("/dev/ttyS0", 19200)
BUFFER = []


def init():
    GPIO.output(RST_PIN, GPIO.LOW)
    time.sleep(0.25)
    GPIO.output(RST_PIN, GPIO.HIGH)
    time.sleep(0.25)


def sendCommand(data, bytesNeed, timeout):
    global BUFFER

    checksum = 0
    sendBuffer = []

    sendBuffer.append(CMD_HEAD)
    for byte in data:
        sendBuffer.append(byte)
        checksum ^= byte
    sendBuffer.append(checksum)
    sendBuffer.append(CMD_TAIL)

    DEVICE.flushInput()
    DEVICE.write(sendBuffer)

    recvBuffer = []
    timeBefore = time.time()
    timeAfter = time.time()
    while timeAfter - timeBefore < timeout and len(recvBuffer) < bytesNeed:
        bytesCanRecv = DEVICE.inWaiting()
        if bytesCanRecv != 0:
            recvBuffer += DEVICE.read(bytesCanRecv)
        timeAfter = time.time()

    if len(recvBuffer) != bytesNeed:
        return ACK_TIMEOUT
    if recvBuffer[0] != CMD_HEAD:
        return ACK_FAIL
    if recvBuffer[bytesNeed - 1] != CMD_TAIL:
        return ACK_FAIL
    if recvBuffer[1] != sendBuffer[1]:
        return ACK_FAIL

    checksum = 0
    for index, byte in enumerate(recvBuffer):
        if index == 0:
            continue
        if index == 6:
            if checksum != byte:
                return ACK_FAIL
            else:
                break
        checksum ^= byte

    BUFFER = recvBuffer

    return ACK_SUCCESS


def buildResponse(status, data):
    return {
        "status": status,
        "data": data
    }


# 取用户总数
def getUserCount():
    global BUFFER

    cmdBuffer = [0x09, 0, 0, 0, 0]
    res = sendCommand(cmdBuffer, 8, 0.1)

    if res == ACK_TIMEOUT:
        return buildResponse(ACK_TIMEOUT, 0)

    if res == ACK_SUCCESS and BUFFER[4] == ACK_SUCCESS:
        return buildResponse(ACK_SUCCESS, BUFFER[3])
    else:
        return buildResponse(res, 0)


# 删除所有用户
def clearAllUser():
    global BUFFER

    cmdBuffer = [0x05, 0, 0, 0, 0]
    res = sendCommand(cmdBuffer, 8, 5)

    if res == ACK_TIMEOUT:
        return buildResponse(ACK_TIMEOUT, False)

    if res == ACK_SUCCESS and BUFFER[4] == ACK_SUCCESS:
        return buildResponse(ACK_SUCCESS, True)
    else:
        return buildResponse(ACK_FAIL, False)


# 比对 1:N
def compareOneToN():
    global BUFFER

    cmdBuffer = [0x0C, 0, 0, 0, 0]
    res = sendCommand(cmdBuffer, 8, 5)

    if res == ACK_TIMEOUT:
        return buildResponse(ACK_TIMEOUT, 0)

    if res == ACK_SUCCESS:
        if BUFFER[4] == ACK_NO_USER:
            return buildResponse(ACK_NO_USER, 0)
        elif BUFFER[4] == ACK_TIMEOUT:
            return buildResponse(ACK_TIMEOUT, 0)

        userID = BUFFER[2] << 8 + BUFFER[3]
        return buildResponse(ACK_SUCCESS, userID)
    else:
        return buildResponse(ACK_FAIL, 0)


# 取指纹特征值并上传
def getFeature():
    global BUFFER

    cmdBuffer = [0x23, 0, 0, 0, 0]
    res = sendCommand(cmdBuffer, 207, 6)

    if res == ACK_TIMEOUT:
        return buildResponse(ACK_TIMEOUT, 0)

    if res == ACK_SUCCESS:
        if BUFFER[4] == ACK_TIMEOUT:
            return buildResponse(ACK_TIMEOUT, 0)
        elif BUFFER[4] == ACK_FAIL:
            return buildResponse(ACK_FAIL, 0)

        feature = BUFFER[12:204]
        return buildResponse(ACK_SUCCESS, feature)
    else:
        return buildResponse(ACK_FAIL, 0)


def main():
    init()
    print(getFeature())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        if DEVICE != None:
            DEVICE.close()
        GPIO.cleanup()
        sys.exit()
