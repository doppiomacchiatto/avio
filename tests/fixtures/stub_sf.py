import sys, os, json, time
D = os.environ.get("STUB_SF_DIR") or os.path.dirname(os.path.abspath(__file__))
mode = open(os.path.join(D, "stub_mode.txt")).read().strip()
open(os.path.join(D, "stub_args.txt"), "w").write(json.dumps(sys.argv[1:]))
open(os.path.join(D, "stub_pid.txt"), "w").write(str(os.getpid()))
if mode == "success":
    print(json.dumps({"status": 0, "result": {"username": "me@example.com", "orgId": "00D000000000001",
                      "accessToken": "SECRET-ACCESS-TOKEN", "refreshToken": "SECRET-REFRESH"}}))
elif mode == "fail":
    print(json.dumps({"status": 1, "name": "AuthError", "message": "user denied access"})); sys.exit(1)
elif mode == "plainerr":
    sys.stderr.write("boom: port 1717 in use\n"); sys.exit(2)
elif mode == "hang":
    time.sleep(120)
