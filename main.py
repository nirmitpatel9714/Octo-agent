"""
Octo Agent — Main Entry Point
===============================
Supports three modes:
  python main.py              → CLI terminal chat (default)
  python main.py web          → Web dashboard + chat
  python main.py mcp-server   → MCP server on stdio
  python main.py onboard      → First-time setup
"""
import sys

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8')
    command = sys.argv[1] if len(sys.argv) > 1 else None

    if command == "web":
        if "--daemon" not in sys.argv:
            import subprocess
            cmd = [sys.executable, sys.argv[0], "web", "--daemon"] + [arg for arg in sys.argv[2:] if arg != "--daemon"]
            kwargs = {}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                kwargs["start_new_session"] = True
                kwargs["stdout"] = subprocess.DEVNULL
                kwargs["stderr"] = subprocess.DEVNULL
            
            subprocess.Popen(cmd, **kwargs)
            
            host = "127.0.0.1"
            port = 8080
            for arg in sys.argv[2:]:
                if arg.startswith("--host="):
                    host = arg.split("=", 1)[1]
                elif arg.startswith("--port="):
                    port = int(arg.split("=", 1)[1])
                    
            print(f"[*] Octo Agent Web Dashboard started in background at http://{host}:{port}")
            sys.exit(0)

        # Launch the web dashboard
        import os
        from pathlib import Path

        # Load .env
        root_path = Path(".").resolve()
        env_file = root_path / ".env"
        if env_file.exists():
            import re
            _ENV_LINE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*=')
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and _ENV_LINE.match(line):
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip("'\""))

        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY", "")
        model = os.getenv("OPENROUTER_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"

        if not api_key:
            print("Error: No API key set. Run 'python main.py onboard' first.")
            print("Set OPENROUTER_API_KEY or OPENAI_API_KEY in .env")
            sys.exit(1)

        # Start heartbeat
        from app.heartbeat import HeartbeatMonitor
        heartbeat = HeartbeatMonitor(root_path, api_key=api_key, model=model)
        heartbeat.start()

        # Start cron scheduler
        from app.cron import CronScheduler
        cron = CronScheduler(root_path)
        cron.start()

        # Start MCP client manager
        from app.mcp_client import MCPManager
        mcp = MCPManager(config_path=root_path / "mcp_config.json")
        mcp.load_config()
        mcp.connect_all()

        # Start MPC orchestrator
        from app.mpc import MPCOrchestrator
        from app.openrouter import OpenRouterClient
        client = OpenRouterClient(api_key, model=model)
        mpc = MPCOrchestrator(client, root_path)

        # Parse optional host/port
        host = "127.0.0.1"
        port = 8080
        for arg in sys.argv[2:]:
            if arg.startswith("--host="):
                host = arg.split("=", 1)[1]
            elif arg.startswith("--port="):
                port = int(arg.split("=", 1)[1])

        print(f"[*] Octo Agent Web Dashboard starting at http://{host}:{port}")
        from app.web.server import run_web_server
        try:
            run_web_server(
                root_path=root_path,
                api_key=api_key,
                model=model,
                host=host,
                port=port,
                heartbeat_monitor=heartbeat,
                cron_scheduler=cron,
                mcp_manager=mcp,
                mpc_orchestrator=mpc,
            )
        finally:
            heartbeat.stop()
            cron.stop()
            mcp.disconnect_all()

    elif command == "mcp-server":
        # Run as MCP server on stdio
        from pathlib import Path
        from app.mcp_server import run_mcp_server
        run_mcp_server(cwd=str(Path(".").resolve()))

    else:
        # Default: CLI mode
        from app.cli import main
        main()
