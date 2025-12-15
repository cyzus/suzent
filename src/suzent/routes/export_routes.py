"""
Data export/import API routes for Suzent.
"""
import json
import tempfile
from pathlib import Path
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from suzent.database import ChatDatabase
from suzent.export_import import (
    export_chat_to_json,
    export_chat_to_markdown,
    export_all_chats,
    import_chat_from_json,
    backup_database,
    get_database_stats,
)
from suzent.logger import get_logger

logger = get_logger(__name__)
db = ChatDatabase()


async def export_chat(request: Request) -> Response:
    """
    Export a specific chat.
    
    Query params:
        - chat_id: ID of chat to export
        - format: 'json' or 'markdown' (default: json)
    """
    try:
        chat_id = request.query_params.get("chat_id")
        format = request.query_params.get("format", "json").lower()
        
        if not chat_id:
            return JSONResponse(
                {"error": "Missing chat_id parameter"},
                status_code=400,
            )
        
        if format == "json":
            data = export_chat_to_json(db, chat_id)
            chat_title = data["title"]
            
            # Return as downloadable file
            json_str = json.dumps(data, indent=2, ensure_ascii=False)
            return Response(
                content=json_str,
                media_type="application/json",
                headers={
                    "Content-Disposition": f'attachment; filename="chat_{chat_id[:8]}_{chat_title[:30]}.json"'
                },
            )
        
        elif format == "markdown":
            markdown = export_chat_to_markdown(db, chat_id)
            chat = db.get_chat(chat_id)
            chat_title = chat["title"] if chat else "chat"
            
            return Response(
                content=markdown,
                media_type="text/markdown",
                headers={
                    "Content-Disposition": f'attachment; filename="chat_{chat_id[:8]}_{chat_title[:30]}.md"'
                },
            )
        
        else:
            return JSONResponse(
                {"error": f"Unsupported format: {format}. Use 'json' or 'markdown'"},
                status_code=400,
            )
    
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except Exception as e:
        logger.error(f"Error exporting chat: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


async def export_all(request: Request) -> Response:
    """
    Export all chats as a ZIP archive.
    """
    try:
        import zipfile
        from io import BytesIO
        
        # Create temporary directory for exports
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Export all chats
            exported_files = export_all_chats(db, temp_path)
            
            # Create ZIP archive
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for file_path in exported_files:
                    file_path = Path(file_path)
                    zip_file.write(file_path, file_path.name)
            
            zip_buffer.seek(0)
            
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            return Response(
                content=zip_buffer.getvalue(),
                media_type="application/zip",
                headers={
                    "Content-Disposition": f'attachment; filename="suzent_chats_{timestamp}.zip"'
                },
            )
    
    except Exception as e:
        logger.error(f"Error exporting all chats: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


async def import_chat(request: Request) -> Response:
    """
    Import a chat from JSON.
    
    Body: JSON chat data
    Query params:
        - preserve_id: 'true' to keep original chat ID (default: false)
    """
    try:
        body = await request.json()
        preserve_id = request.query_params.get("preserve_id", "false").lower() == "true"
        
        chat_id = import_chat_from_json(db, body, preserve_id=preserve_id)
        
        return JSONResponse({
            "success": True,
            "chat_id": chat_id,
            "message": "Chat imported successfully",
        })
    
    except Exception as e:
        logger.error(f"Error importing chat: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


async def create_backup(request: Request) -> Response:
    """
    Create a database backup.
    """
    try:
        # Create backup in a temp directory
        with tempfile.TemporaryDirectory() as temp_dir:
            backup_path = backup_database(db.db_path, Path(temp_dir))
            
            # Read backup file
            with open(backup_path, 'rb') as f:
                backup_data = f.read()
            
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            return Response(
                content=backup_data,
                media_type="application/x-sqlite3",
                headers={
                    "Content-Disposition": f'attachment; filename="suzent_backup_{timestamp}.db"'
                },
            )
    
    except Exception as e:
        logger.error(f"Error creating backup: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


async def get_stats(request: Request) -> Response:
    """
    Get database statistics.
    """
    try:
        stats = get_database_stats(db)
        return JSONResponse(stats)
    
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
