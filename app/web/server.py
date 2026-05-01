"""
Octo Agent — Web Server
========================
FastAPI-based web server providing REST API + WebSocket for the
dashboard and chat interface.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
    from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
    import uvicorn
except ImportError:
    raise ImportError("Install fastapi and uvicorn: pip install fastapi uvicorn[standard]")

from app.agent_state import AgentState
from app.openrouter import OpenRouterClient
from app.tools import build_default_registry
from app.engine import run_agent_turn as _cli_run_agent_turn


def create_app(
    root_path: Path,
    api_key: str,
    model: str = "gpt-4o-mini",
    heartbeat_monitor=None,
    cron_scheduler=None,
    mcp_manager=None,
    mpc_orchestrator=None,
) -> FastAPI:
    app = FastAPI(title="Octo Agent Dashboard", version="2.0.0")

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Shared state
    state = AgentState(root_path)
    client = OpenRouterClient(api_key, model=model)
    registry = build_default_registry()
    cwd = str(root_path)

    # ── Pages ────────────────────────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return (static_dir / "index.html").read_text(encoding="utf-8")

    # ── REST API ─────────────────────────────────────────────────────

    @app.get("/api/status")
    async def api_status():
        latest_hb = heartbeat_monitor.latest if heartbeat_monitor else None
        return {
            "status": "running",
            "model": client.model,
            "uptime": heartbeat_monitor.uptime if heartbeat_monitor else 0,
            "heartbeat": latest_hb,
            "cron_jobs": len(cron_scheduler.list_jobs()) if cron_scheduler else 0,
            "mcp_servers": mcp_manager.status() if mcp_manager else [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @app.get("/api/heartbeats")
    async def api_heartbeats():
        if not heartbeat_monitor:
            return {"history": []}
        return {"history": heartbeat_monitor.history[-50:]}

    @app.get("/api/cron")
    async def api_cron_list():
        if not cron_scheduler:
            return {"jobs": []}
        return {"jobs": [j.to_dict() for j in cron_scheduler.list_jobs()]}

    @app.post("/api/cron")
    async def api_cron_add(request: Request):
        if not cron_scheduler:
            return JSONResponse({"error": "Cron not available"}, 400)
        body = await request.json()
        job = cron_scheduler.add_job(
            name=body.get("name", "Untitled"),
            schedule=body.get("schedule", "every 5m"),
            prompt=body.get("prompt", ""),
        )
        return {"job": job.to_dict()}

    @app.delete("/api/cron/{job_id}")
    async def api_cron_remove(job_id: str):
        if not cron_scheduler:
            return JSONResponse({"error": "Cron not available"}, 400)
        ok = cron_scheduler.remove_job(job_id)
        return {"removed": ok}

    @app.post("/api/cron/{job_id}/toggle")
    async def api_cron_toggle(job_id: str):
        if not cron_scheduler:
            return JSONResponse({"error": "Cron not available"}, 400)
        new_state = cron_scheduler.toggle_job(job_id)
        return {"enabled": new_state}

    @app.get("/api/mcp")
    async def api_mcp_status():
        if not mcp_manager:
            return {"servers": []}
        return {"servers": mcp_manager.status()}

    @app.get("/api/mpc/agents")
    async def api_mpc_agents():
        if not mpc_orchestrator:
            return {"agents": []}
        return {"agents": mpc_orchestrator.list_agents()}

    @app.post("/api/mpc/pipeline")
    async def api_mpc_pipeline(request: Request):
        if not mpc_orchestrator:
            return JSONResponse({"error": "MPC not available"}, 400)
        body = await request.json()
        agents = body.get("agents", [])
        task = body.get("task", "")
        results = mpc_orchestrator.create_pipeline(agents, task)
        return {"results": [{"agent": r.agent, "content": r.content, "step": r.step} for r in results]}

    @app.post("/api/mpc/debate")
    async def api_mpc_debate(request: Request):
        if not mpc_orchestrator:
            return JSONResponse({"error": "MPC not available"}, 400)
        body = await request.json()
        agents = body.get("agents", [])
        task = body.get("task", "")
        rounds = body.get("rounds", 2)
        results = mpc_orchestrator.create_debate(agents, task, rounds)
        return {"results": [{"agent": r.agent, "content": r.content, "step": r.step} for r in results]}

    # ── Management APIs ──────────────────────────────────────────────

    @app.get("/api/settings")
    async def api_get_settings():
        env_file = root_path / ".env"
        settings = {"OPENAI_API_KEY": "", "OPENAI_MODEL": "", "OPENROUTER_API_KEY": "", "OPENROUTER_MODEL": ""}
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    if k in settings:
                        settings[k] = v.strip().strip("'\"")
        return settings

    @app.post("/api/settings")
    async def api_set_settings(request: Request):
        body = await request.json()
        env_file = root_path / ".env"
        # read existing
        lines = []
        if env_file.exists():
            lines = env_file.read_text(encoding="utf-8").splitlines()
        
        # update lines
        for k, v in body.items():
            if k in ["OPENAI_API_KEY", "OPENAI_MODEL", "OPENROUTER_API_KEY", "OPENROUTER_MODEL"]:
                found = False
                for i, line in enumerate(lines):
                    if line.startswith(f"{k}="):
                        lines[i] = f"{k}={v}"
                        found = True
                        break
                if not found:
                    lines.append(f"{k}={v}")
        
        env_file.write_text("\n".join(lines), encoding="utf-8")
        return {"status": "ok"}

    @app.get("/api/agents")
    async def api_get_agents():
        agents_dir = root_path / "agents"
        agents = []
        if agents_dir.exists():
            for f in agents_dir.glob("*.md"):
                agents.append({"name": f.stem, "content": f.read_text(encoding="utf-8")})
        return {"agents": agents}

    @app.post("/api/agents")
    async def api_save_agent(request: Request):
        body = await request.json()
        name = body.get("name")
        content = body.get("content", "")
        if not name:
            return JSONResponse({"error": "Name required"}, 400)
        agents_dir = root_path / "agents"
        agents_dir.mkdir(exist_ok=True)
        (agents_dir / f"{name}.md").write_text(content, encoding="utf-8")
        return {"status": "ok"}

    @app.delete("/api/agents/{name}")
    async def api_delete_agent(name: str):
        agent_file = root_path / "agents" / f"{name}.md"
        if agent_file.exists():
            agent_file.unlink()
        return {"status": "ok"}

    @app.get("/api/skills")
    async def api_get_skills():
        skills_dir = root_path / "skills"
        skills = []
        if skills_dir.exists():
            for f in skills_dir.glob("*.md"):
                skills.append({"name": f.stem, "content": f.read_text(encoding="utf-8")})
        return {"skills": skills}

    @app.post("/api/skills")
    async def api_save_skill(request: Request):
        body = await request.json()
        name = body.get("name")
        content = body.get("content", "")
        if not name:
            return JSONResponse({"error": "Name required"}, 400)
        skills_dir = root_path / "skills"
        skills_dir.mkdir(exist_ok=True)
        (skills_dir / f"{name}.md").write_text(content, encoding="utf-8")
        return {"status": "ok"}

    @app.delete("/api/skills/{name}")
    async def api_delete_skill(name: str):
        skill_file = root_path / "skills" / f"{name}.md"
        if skill_file.exists():
            skill_file.unlink()
        return {"status": "ok"}

    @app.get("/api/files/{name}")
    async def api_get_file(name: str):
        if name not in ["memory.md", "soul.md", "OCTO.md"]:
            return JSONResponse({"error": "Invalid file"}, 400)
        file_path = root_path / name
        content = file_path.read_text(encoding="utf-8") if file_path.exists() else ""
        return {"name": name, "content": content}

    @app.post("/api/files/{name}")
    async def api_save_file(name: str, request: Request):
        if name not in ["memory.md", "soul.md", "OCTO.md"]:
            return JSONResponse({"error": "Invalid file"}, 400)
        body = await request.json()
        content = body.get("content", "")
        (root_path / name).write_text(content, encoding="utf-8")
        return {"status": "ok"}

    @app.get("/api/conversations")
    async def api_conversations():
        chats_dir = root_path / "chats"
        convos = []
        if chats_dir.exists():
            for f in sorted(chats_dir.glob("chat_*.md"), reverse=True):
                # Read first few lines to get a preview
                try:
                    text = f.read_text(encoding="utf-8")
                    lines = text.strip().splitlines()
                    preview = ""
                    for line in lines[1:]:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            preview = line[:80]
                            break
                except OSError:
                    preview = ""
                convos.append({
                    "id": f.stem,
                    "name": f.stem,
                    "file": f.name,
                    "preview": preview,
                    "size": f.stat().st_size,
                })
        return {"conversations": convos[:50]}

    @app.get("/api/conversations/{conv_id}")
    async def api_conversation_detail(conv_id: str):
        chats_dir = root_path / "chats"
        chat_file = chats_dir / f"{conv_id}.md"
        if not chat_file.exists():
            return JSONResponse({"error": "Conversation not found"}, 404)
        content = chat_file.read_text(encoding="utf-8")
        return {"id": conv_id, "content": content}

    @app.delete("/api/conversations/{conv_id}")
    async def api_delete_conversation(conv_id: str):
        chats_dir = root_path / "chats"
        chat_file = chats_dir / f"{conv_id}.md"
        if chat_file.exists():
            chat_file.unlink()
            return {"status": "ok"}
        return JSONResponse({"error": "Conversation not found"}, 404)

    @app.post("/api/conversations")
    async def api_create_conversation():
        """Create a new conversation and return its ID."""
        new_state = AgentState(root_path)
        return {"id": new_state.session_id, "file": new_state.session_file.name}

    # ── WebSocket Chat ───────────────────────────────────────────────

    @app.websocket("/ws/chat")
    async def ws_chat(websocket: WebSocket):
        await websocket.accept()
        # Each WS connection gets its own state
        ws_state = AgentState(root_path)
        ws_client = OpenRouterClient(api_key, model=model)
        ws_registry = build_default_registry()

        try:
            while True:
                data = await websocket.receive_text()
                msg = json.loads(data)
                user_text = msg.get("content", "").strip()
                if not user_text:
                    continue

                ws_state.record_message("user", user_text)

                # Run the agent turn in a thread to not block
                def _run():
                    tool_schemas = ws_registry.openai_schemas()
                    tool_events = []
                    for _ in range(20):
                        resp = ws_client.chat_with_tools(ws_state.messages, tools=tool_schemas)
                        tool_calls = resp.get("tool_calls") or []
                        content = (resp.get("content") or "").strip()

                        if not tool_calls:
                            if content:
                                ws_state.record_message("assistant", content)
                            return {"content": content or "", "tools": tool_events}

                        ws_state.messages.append(resp)
                        for tc in tool_calls:
                            func = tc.get("function", {})
                            tn = func.get("name", "unknown")
                            try:
                                ta = json.loads(func.get("arguments", "{}"))
                            except json.JSONDecodeError:
                                ta = {}
                            result = ws_registry.execute(tn, ta, cwd=cwd)
                            tool_events.append({"tool": tn, "result": result[:500]})
                            ws_state.messages.append({
                                "role": "tool",
                                "tool_call_id": tc.get("id", ""),
                                "content": result,
                            })
                    return {"content": "Reached max iterations.", "tools": tool_events}

                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(None, _run)
                await websocket.send_text(json.dumps({
                    "role": "assistant",
                    "content": result["content"],
                    "tools": result.get("tools", []),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }))

        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    # ── WebSocket Terminal ────────────────────────────────────────────

    @app.websocket("/ws/terminal")
    async def ws_terminal(websocket: WebSocket):
        await websocket.accept()
        import subprocess as sp
        try:
            while True:
                data = await websocket.receive_text()
                msg = json.loads(data)
                command = msg.get("command", "").strip()
                if not command:
                    continue
                # Execute in thread
                def _exec():
                    try:
                        result = sp.run(
                            command, shell=True, cwd=str(root_path),
                            capture_output=True, text=True, timeout=60,
                        )
                        out = ""
                        if result.stdout:
                            out += result.stdout
                        if result.stderr:
                            out += ("\n" if out else "") + result.stderr
                        return {"output": out or "(no output)", "exit_code": result.returncode}
                    except sp.TimeoutExpired:
                        return {"output": "Error: Command timed out after 60s.", "exit_code": -1}
                    except Exception as e:
                        return {"output": f"Error: {e}", "exit_code": -1}

                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(None, _exec)
                await websocket.send_text(json.dumps(result))
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    return app


def run_web_server(
    root_path: Path,
    api_key: str,
    model: str = "gpt-4o-mini",
    host: str = "127.0.0.1",
    port: int = 8080,
    heartbeat_monitor=None,
    cron_scheduler=None,
    mcp_manager=None,
    mpc_orchestrator=None,
) -> None:
    app = create_app(
        root_path=root_path,
        api_key=api_key,
        model=model,
        heartbeat_monitor=heartbeat_monitor,
        cron_scheduler=cron_scheduler,
        mcp_manager=mcp_manager,
        mpc_orchestrator=mpc_orchestrator,
    )
    uvicorn.run(app, host=host, port=port, log_level="info")
