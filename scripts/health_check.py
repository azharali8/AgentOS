import sys
import httpx

def main():
    try:
        r = httpx.get("http://127.0.0.1:8000/health")
        if r.status_code == 200:
            print("Health check passed.")
            sys.exit(0)
    except Exception as e:
        print(f"Health check failed: {e}")
    sys.exit(1)

if __name__ == "__main__":
    main()
