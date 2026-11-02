"""IMAP modified UTF-7 (RFC 3501 §5.1.3), the encoding of non-ASCII folder names."""

import base64


def decode_mutf7(name: str) -> str:
    decoded: list[str] = []
    index = 0
    while index < len(name):
        if name[index] != "&":
            decoded.append(name[index])
            index += 1
            continue
        end = name.index("-", index)
        chunk = name[index + 1 : end]
        if chunk:
            padded = chunk.replace(",", "/") + "=" * (-len(chunk) % 4)
            decoded.append(base64.b64decode(padded).decode("utf-16-be"))
        else:
            decoded.append("&")  # "&-" is a literal ampersand
        index = end + 1
    return "".join(decoded)
