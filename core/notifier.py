import requests

# 使用您提供的 Token
TOKEN = "dghhDjmyxYlHfbeTSWwMXA4CXQ23JpJAoUScsIqYn5ppRgvN+/Lnpudp4oLPuVJGdBdF4ysTtc4yBwCxPpI9SPEYEvYHbOz98WwFwZ/UG8gY0jUa+nzU3Ow86O4QNBbuys5eZtebYqKpBnE6UdqzqwdB04t89/1O/w1cDnyilFU="

def send_line(msg):
    url = "https://api.line.me/v2/bot/message/broadcast"
    headers = {
        "Authorization": f"Bearer {TOKEN}", 
        "Content-Type": "application/json"
    }
    data = {
        "messages": [
            {
                "type": "text", 
                "text": msg
            }
        ]
    }
    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code != 200:
            print(f"LINE API Error: {response.status_code} {response.text}")
    except Exception as e:
        print(f"LINE 通知連線失敗: {e}")