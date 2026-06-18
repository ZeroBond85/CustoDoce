"""Test Parelheiros slug."""
import httpx

url = "https://spani-tabloides-bucket.s3.us-east-1.amazonaws.com/tabloides/paralheiros-3xpqbw606muo9vuajitvcl.pdf"
with httpx.Client(timeout=15, follow_redirects=True, verify=False) as client:
    r = client.head(url)
    ct = r.headers.get("content-type", "")
    cl = r.headers.get("content-length", "?")
    print(f"{r.status_code} {ct} ({cl} bytes)")
