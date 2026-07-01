from flask import Flask, request, jsonify
import asyncio, json, requests, aiohttp, binascii
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import like_pb2, uid_generator_pb2, visit_count_pb2
from google.protobuf.message import DecodeError
from collections import OrderedDict

app = Flask(__name__)

VALID_API_KEYS = {"ZEXXY"}
daily_limit = 100
used_count = 0

def load_tokens(region):
    try:
        if region == "SG":
            with open("token_sg.json", "r") as f:
                tokens = json.load(f)
        elif region == "IND":
            with open("token_ind.json", "r") as f:
                tokens = json.load(f)
        elif region in {"BR","US","SAC","NA"}:
            with open("token_br.json", "r") as f:
                tokens = json.load(f)
        else:
            with open("token_bd.json", "r") as f:
                tokens = json.load(f)
        return tokens
    except Exception as e:
        app.logger.error(f"Error loading tokens: {e}")
        return None

def encrypt_message(plaintext):
    key = b'Yg&tc%DEuh6%Zc^8'
    iv = b'6oyZDr22E3ychjM%'
    cipher = AES.new(key, AES.MODE_CBC, iv)
    padded = pad(plaintext, AES.block_size)
    return binascii.hexlify(cipher.encrypt(padded)).decode('utf-8')

def create_protobuf_message(uid, region):
    msg = like_pb2.like()
    msg.uid = int(uid)
    msg.region = region
    return msg.SerializeToString()

async def send_request(encrypted_uid, token, url):
    edata = bytes.fromhex(encrypted_uid)
    headers = {"Authorization": f"Bearer {token}"}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=edata, headers=headers) as resp:
            return await resp.text()

async def send_multiple_requests(uid, region, url):
    protobuf = create_protobuf_message(uid, region)
    encrypted_uid = encrypt_message(protobuf)
    tokens = load_tokens(region)
    tasks = [send_request(encrypted_uid, t["token"], url) for t in tokens]
    return await asyncio.gather(*tasks)

def create_uid_proto(uid):
    msg = uid_generator_pb2.uid_generator()
    msg.saturn_ = int(uid)
    msg.garena = 1
    return msg.SerializeToString()

def enc(uid):
    return encrypt_message(create_uid_proto(uid))

def make_request(encrypt, region, token):
    if region == "SG":
        url = "https://client.sg.freefiremobile.com/GetPlayerPersonalShow"
    elif region == "IND":
        url = "https://client.ind.freefiremobile.com/GetPlayerPersonalShow"
    elif region in {"BR","US","SAC","NA"}:
        url = "https://client.us.freefiremobile.com/GetPlayerPersonalShow"
    else:
        url = "https://clientbp.ggpolarbear.com/GetPlayerPersonalShow"
    edata = bytes.fromhex(encrypt)
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.post(url, data=edata, headers=headers, verify=False)
    decoded = visit_count_pb2.Info()
    decoded.ParseFromString(resp.content)
    return decoded

@app.route('/like', methods=['GET'])
def like_handler():
    global used_count
    api_key = request.args.get("key")
    if api_key not in VALID_API_KEYS:
        return {"error":"Invalid API key"},401
    uid = request.args.get("uid")
    region = request.args.get("region","").upper()
    if not uid or not region:
        return {"error":"UID and region required"},400
    tokens = load_tokens(region)
    token = tokens[0]["token"]
    encrypted_uid = enc(uid)
    before = make_request(encrypted_uid, region, token)
    before_like = before.AccountInfo.Likes
    if region == "SG":
        url = "https://client.sg.freefiremobile.com/LikeProfile"
    elif region == "IND":
        url = "https://client.ind.freefiremobile.com/LikeProfile"
    elif region in {"BR","US","SAC","NA"}:
        url = "https://client.us.freefiremobile.com/LikeProfile"
    else:
        url = "https://clientbp.ggpolarbear.com/LikeProfile"
    asyncio.run(send_multiple_requests(uid, region, url))
    after = make_request(encrypted_uid, region, token)
    after_like = after.AccountInfo.Likes
    like_given = after_like - before_like
    status = 1 if like_given>0 else 2
    if status==1: used_count+=1
    remaining = max(daily_limit-used_count,0)
    result = OrderedDict([
        ("LikesGivenByAPI",like_given),
        ("LikesafterCommand",after_like),
        ("LikesbeforeCommand",before_like),
        ("PlayerNickname",after.AccountInfo.PlayerNickname),
        ("Level",after.AccountInfo.Levels),
        ("Region",after.AccountInfo.PlayerRegion),
        ("UID",after.AccountInfo.UID),
        ("status",status),
        ("daily_limit",daily_limit),
        ("used",used_count),
        ("remaining",remaining)
    ])
    return jsonify(result)

@app.route('/remain', methods=['GET'])
def remain_info():
    global used_count
    return jsonify({
        "daily_limit":daily_limit,
        "remaining":max(daily_limit-used_count,0),
        "used":used_count,
        "reset_info":"4:00 AM IST"
    })

if __name__=="__main__":
    app.run(debug=True,use_reloader=False)
