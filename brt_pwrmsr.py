#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function

import sys
import os
import serial
import threading
import time
from datetime import datetime

def thread_write():
    print("=== WRITE THREAD START ===")
    # ECHONET Lite フレーム作成
    # 　参考資料
    # 　・ECHONET-Lite_Ver.1.12_02.pdf (以下 EL)
    # 　・Appendix_H.pdf (以下 AppH)
    echonetLiteFrame = ""
    echonetLiteFrame += "\x10\x81"      # EHD (参考:EL p.3-2)
    echonetLiteFrame += "\x00\x01"      # TID (参考:EL p.3-3)
    # ここから EDATA
    echonetLiteFrame += "\x05\xFF\x01"  # SEOJ (参考:EL p.3-3 AppH p.3-408～)
    echonetLiteFrame += "\x02\x88\x01"  # DEOJ (参考:EL p.3-3 AppH p.3-274～)
    echonetLiteFrame += "\x62"          # ESV(62:プロパティ値読み出し要求) (参考:EL p.3-5)
    echonetLiteFrame += "\x01"          # OPC(1個)(参考:EL p.3-7)
    echonetLiteFrame += "\xE7"          # EPC(参考:EL p.3-7 AppH p.3-275)
    echonetLiteFrame += "\x00"          # PDC(参考:EL p.3-9)

    # コマンド生成
    command = "SKSENDTO 1 {0} 0E1A 1 {1:04X} {2}".format(ipv6Addr, len(echonetLiteFrame), echonetLiteFrame)

    while not stop_write_event.is_set():
        print("--- SEND CMD ---")
        ser.write(command)
        time.sleep(5)
    print("=== WRITE THREAD END ===")

def thread_read():
    print("=== READ THREAD START ===")
    f = open('test.log', 'w')
    while not stop_read_event.is_set():
        line = ser.readline()
        print(line, end="") # エコーバック
        if line.startswith("ERXUDP") :
            cols = line.strip().split(' ')
            res = cols[8]   # UDP受信データ部分
            #tid = res[4:4+4];
            seoj = res[8:8+6]
            #deoj = res[14,14+6]
            ESV = res[20:20+2]
            #OPC = res[22,22+2]
            if seoj == "028801" and ESV == "72" :
                # スマートメーター(028801)から来た応答(72)なら
                EPC = res[24:24+2]
                if EPC == "E7" :
                    # 内容が瞬時電力計測値(E7)だったら
                    hexPower = line[-8:]    # 最後の4バイト（16進数で8文字）が瞬時電力計測値
                    intPower = int(hexPower, 16)
                    print(u"瞬時電力計測値:{0}[W]".format(intPower))
                    print("now:" + datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
                    f.write(datetime.now().strftime("%Y/%m/%d %H:%M:%S") + u", {0}".format(intPower) + "\n")
    f.close()
    print("=== READ THREAD END ===")

# Bルート認証ID
rbid  = os.environ.get('RBID')
if(rbid is None):
    print("Please set RBID")
    sys.exit()
# Bルート認証パスワード
rbpwd = os.environ.get('RBPWD')
if(rbpwd is None):
    print("Please set RBPWD")
    sys.exit()
 
# シリアルポートデバイス名
serialPortDev = '/dev/ttyUSB0'  # Linux(ラズパイなど）の場合

# シリアルポート初期化
ser = serial.Serial(serialPortDev, 115200)

print("--- VERSION ---")
# とりあえずバージョンを取得してみる（やらなくてもOK）
ser.write("SKVER\r\n")
# print(ser.readline(), end="") # エコーバック
ser.readline()
print(ser.readline(), end="") # バージョン

print("--- SET PWD ---")
# Bルート認証パスワード設定
ser.write("SKSETPWD C " + rbpwd + "\r\n")
print(ser.readline(), end="") # OKが来るはず（チェック無し）
# print(ser.readline(), end="") # エコーバック
ser.readline()

print("--- SET ID ---")
# Bルート認証ID設定
ser.write("SKSETRBID " + rbid + "\r\n")
print(ser.readline(), end="") # OKが来るはず（チェック無し）
# print(ser.readline(), end="") # エコーバック
ser.readline()

scanDuration = 6;   # スキャン時間
scanRes = {} # スキャン結果の入れ物

print("--- SCAN ---")
# スキャンのリトライループ（何か見つかるまで）
while not scanRes.has_key("Channel") :
    # アクティブスキャン（IE あり）を行う
    # 時間かかります。10秒ぐらい？
    ser.write("SKSCAN 2 FFFFFFFF " + str(scanDuration) + "\r\n")

    # スキャン1回について、スキャン終了までのループ
    scanEnd = False
    while not scanEnd :
        line = ser.readline()
        print(line, end="")

        if line.startswith("EVENT 22") :
            # スキャン終わったよ（見つかったかどうかは関係なく）
            scanEnd = True
        elif line.startswith("  ") :
            # スキャンして見つかったらスペース2個あけてデータがやってくる
            # 例
            #  Channel:39
            #  Channel Page:09
            #  Pan ID:FFFF
            #  Addr:FFFFFFFFFFFFFFFF
            #  LQI:A7
            #  PairID:FFFFFFFF
            cols = line.strip().split(':')
            scanRes[cols[0]] = cols[1]
    scanDuration+=1

    if 7 < scanDuration and not scanRes.has_key("Channel"):
        # 引数としては14まで指定できるが、7で失敗したらそれ以上は無駄っぽい
        print("スキャンリトライオーバー")
        sys.exit()  #### 終了 ####

print("--- SET CHANNEL ---")
# スキャン結果からChannelを設定。
ser.write("SKSREG S2 " + scanRes["Channel"] + "\r\n")
print(ser.readline(), end="") # エコーバック
print(ser.readline(), end="") # OKが来るはず（チェック無し）

print("--- SET PAN ID ---")
# スキャン結果からPan IDを設定
ser.write("SKSREG S3 " + scanRes["Pan ID"] + "\r\n")
print(ser.readline(), end="") # エコーバック
print(ser.readline(), end="") # OKが来るはず（チェック無し）

print("--- SET ADDRES ---")
# MACアドレス(64bit)をIPV6リンクローカルアドレスに変換。
# (BP35A1の機能を使って変換しているけど、単に文字列変換すればいいのではという話も？？)
ser.write("SKLL64 " + scanRes["Addr"] + "\r\n")
print(ser.readline(), end="") # エコーバック
ipv6Addr = ser.readline().strip()
print(ipv6Addr)

print("--- START SKJOIN ---")
# PANA 接続シーケンスを開始します。
ser.write("SKJOIN " + ipv6Addr + "\r\n");
print(ser.readline(), end="") # エコーバック
print(ser.readline(), end="") # OKが来るはず（チェック無し）

# PANA 接続完了待ち（10行ぐらいなんか返してくる）
bConnected = False
while not bConnected :
    line = ser.readline()
    print(line, end="")
    if line.startswith("EVENT 24") :
        print("PANA 接続失敗")
        sys.exit()  #### 糸冬了 ####
    elif line.startswith("EVENT 25") :
        # 接続完了！
        bConnected = True

print("--- SKJOIN SUCCESS!! ---")

# これ以降、シリアル通信のタイムアウトを設定
ser.timeout = 2

# スマートメーターがインスタンスリスト通知を投げてくる
# (ECHONET-Lite_Ver.1.12_02.pdf p.4-16)
print(ser.readline(), end="") #無視

print("--- START KEISOKU ---")
stop_read_event = threading.Event()
stop_write_event = threading.Event()
t_read = threading.Thread(target=thread_read)
t_write = threading.Thread(target=thread_write)
t_read.start()
t_write.start()

while True:
    key = raw_input()
    if(key=="q"):
        print("=== QUIT START ===")
        stop_write_event.set()
        t_write.join()
        print("--- t_write joined!! ---")
        stop_read_event.set()
        t_read.join()
        print("--- t_read joined!! ---")
        print("=== QUIT END ===")
        exit()

ser.close()
