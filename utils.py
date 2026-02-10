BASE62 = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

def encode_base62(num: int) -> str:
    if num == 0:
        return BASE62[0]
    arr = []
    while num:
        num, rem = divmod(num, 62)
        arr.append(BASE62[rem])
    return ''.join(reversed(arr))

def decode_base62(s: str) -> int:
    num = 0
    for char in s:
        num = num * 62 + BASE62.index(char)
    return num
