def http_to_ws_url(http_url: str) -> str:
    """LiveKit browser SDK connects with ws:// or wss://, not http(s)://."""
    u = http_url.strip().rstrip('/')
    if u.startswith('https://'):
        return 'wss://' + u[8:]
    if u.startswith('http://'):
        return 'ws://' + u[7:]
    return u
