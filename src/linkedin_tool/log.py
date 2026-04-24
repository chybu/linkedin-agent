ANNOUNCEMENT_WIDTH = 48


def print_message(title:str, info:str=""):
    print(f"{title.ljust(20, '-')} {info}")
    
def print_announcement(title:str, info:str=""):
    banner = f" {title.strip().upper()} ".center(ANNOUNCEMENT_WIDTH, "=")
    print()
    print(banner)
    if info:
        print(info)
    print("=" * ANNOUNCEMENT_WIDTH)
