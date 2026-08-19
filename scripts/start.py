import subprocess
def main():
    subprocess.run(["uvicorn", "backend.app.main:app", "--reload"])
if __name__ == "__main__":
    main()
