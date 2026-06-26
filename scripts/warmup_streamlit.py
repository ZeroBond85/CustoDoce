import httpx, time, sys

url = sys.argv[1] if len(sys.argv) > 1 else "https://custodoce.streamlit.app"
print(f"Warming up {url}...")
for i in range(6):
    try:
        r = httpx.get(url, timeout=30)
        print(f"Attempt {i+1}: HTTP {r.status_code}")
        if r.status_code in (200, 303):
            print("App is awake!")
            break
    except Exception as e:
        print(f"Attempt {i+1}: {e}")
    time.sleep(15)
