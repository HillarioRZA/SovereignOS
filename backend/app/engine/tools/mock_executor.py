"""
Mock Tool Executor.
Menyediakan simulator eksekusi perkakas deterministik untuk fase 1 dan 2 sebelum sandbox penuh.
"""

from typing import Any, Dict
from app.core.logger import logger


class MockToolExecutor:
    """Eksekutor perkakas mock in-memory untuk pengujian alur giliran turn loop."""

    def __init__(self) -> None:
        self.virtual_fs: Dict[str, str] = {
            "README.md": "# Project Sovereign Test\nSample project.",
            "main.py": "print('Hello, Sovereign OS!')\n",
        }

    async def execute(self, tool_id: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Mengeksekusi pemanggilan perkakas secara aman in-memory."""
        logger.info(f"[MockToolExecutor] Menjalankan perkakas [{tool_id}] dengan args: {arguments}")

        if tool_id == "builtin:read_file":
            path = arguments.get("file_path", "")
            if path in self.virtual_fs:
                return {"status": "success", "content": self.virtual_fs[path]}
            return {"status": "error", "error": f"File not found: {path}"}

        elif tool_id == "builtin:write_file":
            path = arguments.get("file_path", "")
            content = arguments.get("content", "")
            self.virtual_fs[path] = content
            return {"status": "success", "message": f"File written successfully: {path}", "bytes": len(content)}

        elif tool_id == "builtin:list_directory":
            files = list(self.virtual_fs.keys())
            return {"status": "success", "files": files, "count": len(files)}

        elif tool_id == "builtin:search_files":
            query = arguments.get("query", "").lower()
            matches = [p for p, content in self.virtual_fs.items() if query in p.lower() or query in content.lower()]
            return {"status": "success", "matches": matches, "count": len(matches)}

        elif tool_id == "ptc:execute_code":
            code = arguments.get("code", "")
            # Simulasi output eksekusi
            return {
                "status": "success",
                "stdout": f"[Mock PTC Output] Executed {len(code)} bytes successfully.\nResult: OK",
                "return_code": 0,
            }

        return {"status": "error", "error": f"Unsupported mock tool: {tool_id}"}
