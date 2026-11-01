import subprocess

# Get raw bytes from git
result = subprocess.run(
    ['git', '-C', r'D:\work\jia_mo\P50w\STM32g474vet6_focP50w', 'show', 'HEAD:STM32g474vet6_focP50w/Core/Src/main.c'],
    capture_output=True
)
content_bytes = result.stdout

# The git storage has corrupted GBK encoding
# Let's try to reconstruct from the bytes

# Looking at the bytes, we see patterns like:
# EF BF BD = UTF-8 replacement character (U+FFFD)
# These are where GBK bytes were incorrectly converted

# Strategy: Re-interpret the bytes
# The corruption: GBK bytes -> incorrectly treated as UTF-8 -> replaced invalid sequences

# To reverse: We need to find the original GBK bytes
# But we can't fully recover them from UTF-8 replacement chars

# Alternative: Use a heuristic approach
# GBK Chinese characters map to specific byte ranges
# 0x81-0xFE for first byte, 0x40-0xFE (excluding 0x7F) for second byte

def is_gbk_lead(b):
    return 0x81 <= b <= 0xFE

def is_gbk_trail(b):
    return 0x40 <= b <= 0xFE and b != 0x7F

def reconstruct_gbk(content_bytes):
    """Try to find and reconstruct GBK sequences"""
    result = bytearray()
    i = 0
    while i < len(content_bytes):
        # Skip UTF-8 BOM
        if content_bytes[i] == 0xEF and i+2 < len(content_bytes):
            if content_bytes[i+1] == 0xBB and content_bytes[i+2] == 0xBF:
                i += 3
                continue
        
        # Skip replacement characters
        if content_bytes[i] == 0xEF and i+2 < len(content_bytes):
            if content_bytes[i+1] == 0xBF and content_bytes[i+2] == 0xBD:
                i += 3
                continue
        
        result.append(content_bytes[i])
        i += 1
    
    return bytes(result)

clean_bytes = reconstruct_gbk(content_bytes)

# Try GBK decode
try:
    content = clean_bytes.decode('gbk')
    print("GBK decode SUCCESS")
except:
    # Last resort: just use the bytes as-is and write as UTF-8
    print("GBK decode failed, using raw bytes")
    # Try to decode what we can
    content = clean_bytes.decode('utf-8', errors='replace')

# Write as UTF-8
with open(r'D:\work\jia_mo\P50w\STM32g474vet6_focP50w\Core\Src\main.c', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done")
