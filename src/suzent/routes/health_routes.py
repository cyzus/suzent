"""
Health check and monitoring endpoints.
"""
import os
import sys
import time
from datetime import datetime
from starlette.requests import Request
from starlette.responses import JSONResponse
from suzent.database import ChatDatabase
from suzent.logger import get_logger

logger = get_logger(__name__)
db = ChatDatabase()
start_time = time.time()


async def health_check(request: Request) -> JSONResponse:
    """
    Basic health check endpoint.
    
    Returns 200 if service is running.
    """
    return JSONResponse({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "uptime_seconds": int(time.time() - start_time),
    })


async def readiness_check(request: Request) -> JSONResponse:
    """
    Readiness check - verifies all dependencies are available.
    
    Returns 200 if service is ready to accept requests.
    """
    checks = {}
    
    # Check database
    try:
        chats = db.list_chats(limit=1)
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)}"
    
    # Check memory system (if enabled)
    try:
        from suzent.config import CONFIG
        if CONFIG.memory_enabled:
            from suzent.agent_manager import memory_manager
            if memory_manager:
                checks["memory_system"] = "ok"
            else:
                checks["memory_system"] = "not initialized"
        else:
            checks["memory_system"] = "disabled"
    except Exception as e:
        checks["memory_system"] = f"error: {str(e)}"
    
    # Determine overall status
    all_ok = all(
        status in ("ok", "disabled", "not initialized") 
        for status in checks.values()
    )
    
    status_code = 200 if all_ok else 503
    
    return JSONResponse(
        {
            "status": "ready" if all_ok else "not ready",
            "checks": checks,
            "timestamp": datetime.now().isoformat(),
        },
        status_code=status_code,
    )


async def get_system_info(request: Request) -> JSONResponse:
    """
    Get system information and statistics.
    """
    try:
        from suzent.config import CONFIG
        from suzent.export_import import get_database_stats
        
        # Get database stats
        db_stats = get_database_stats(db)
        
        # System info
        info = {
            "version": "0.1.0",
            "python_version": sys.version,
            "platform": sys.platform,
            "uptime_seconds": int(time.time() - start_time),
            "database": db_stats,
            "config": {
                "memory_enabled": CONFIG.memory_enabled,
                "default_tools": CONFIG.default_tools,
                "model_count": len(CONFIG.model_options),
            },
        }
        
        return JSONResponse(info)
    
    except Exception as e:
        logger.error(f"Error getting system info: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


async def get_metrics(request: Request) -> JSONResponse:
    """
    Get metrics in Prometheus format (optional).
    """
    try:
        from suzent.export_import import get_database_stats
        
        stats = get_database_stats(db)
        
        # Simple Prometheus-style metrics
        metrics = []
        metrics.append(f"# HELP suzent_chats_total Total number of chats")
        metrics.append(f"# TYPE suzent_chats_total counter")
        metrics.append(f"suzent_chats_total {stats['total_chats']}")
        metrics.append("")
        
        metrics.append(f"# HELP suzent_messages_total Total number of messages")
        metrics.append(f"# TYPE suzent_messages_total counter")
        metrics.append(f"suzent_messages_total {stats['total_messages']}")
        metrics.append("")
        
        metrics.append(f"# HELP suzent_database_size_bytes Database size in bytes")
        metrics.append(f"# TYPE suzent_database_size_bytes gauge")
        metrics.append(f"suzent_database_size_bytes {stats['database_size_bytes']}")
        metrics.append("")
        
        metrics.append(f"# HELP suzent_uptime_seconds Service uptime in seconds")
        metrics.append(f"# TYPE suzent_uptime_seconds counter")
        metrics.append(f"suzent_uptime_seconds {int(time.time() - start_time)}")
        metrics.append("")
        
        return JSONResponse(
            content="\n".join(metrics),
            media_type="text/plain",
        )
    
    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
